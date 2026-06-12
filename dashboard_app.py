"""
==========================================================
  LINKEDIN SCRAPER - PANEL DE CONTROL (Tkinter)
  
  Dashboard visual para controlar el pipeline de scraping,
  deteccion de ofertas y extraccion de correos.
==========================================================
"""

import os
import sys
import re
import json
import random
import csv
import threading
import queue
import time
from pathlib import Path
from datetime import datetime, timedelta
from tkinter import (
    Tk, Toplevel, Frame, Label, Button, Text, Scrollbar, StringVar, IntVar,
    DoubleVar, END, DISABLED, NORMAL, TOP, BOTTOM, LEFT, RIGHT,
    BOTH, X, Y, W, E, N, S, CENTER, HORIZONTAL, VERTICAL, WORD,
    ttk, messagebox, filedialog
)

# --- Playwright ---
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright._impl._errors import TargetClosedError

# --- Modulos locales ---
from process_locations import find_locations_in_text
from detect_jobs import detect_job_offer
from contact_matcher import match_author, is_spam_author, load_contacts
import train_model

# ===================== CONFIGURACION =====================

STATE_FILE = "linkedin_state.json"
ENV_FILE = ".env"
EXTRACTED_FILE = "extracted_posts.json"
LOCATIONS_FILE = "extracted_posts_with_locations.json"
LOCALIDADES_FILE = "localidades.json"
KEYWORDS_FILE = "job_keywords.json"
TRAINING_FILE = "training_data.json"
STRUCTURAL_CSV = "Ofertas_Estructurales.csv"
ALL_OFFERS_CSV = "Todas_Ofertas.csv"

NETWORK_STATS_FILE = "network_stats.json"
LINKEDIN_NETWORK_URL = "https://www.linkedin.com/mynetwork/"

LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"

# ===================== COLORES DARK THEME =====================

COLORS = {
    "bg": "#1a1a2e",
    "bg_card": "#16213e",
    "bg_input": "#0f3460",
    "accent": "#e94560",
    "accent_green": "#00c853",
    "accent_yellow": "#ffd600",
    "accent_blue": "#448aff",
    "text": "#e0e0e0",
    "text_dim": "#8892a0",
    "text_bright": "#ffffff",
    "border": "#2a2a4a",
    "success": "#00e676",
    "warning": "#ffab00",
    "error": "#ff1744",
    "running": "#00c853",
    "stopped": "#ff1744",
    "waiting": "#ffd600",
}

# ===================== UTILIDADES =====================

def load_env(path=ENV_FILE):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def load_json(filepath, default=None):
    if default is None:
        default = []
    p = Path(filepath)
    if not p.exists():
        return default
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_relative_time(time_str):
    try:
        now = datetime.now()
        clean_str = time_str.lower().replace(":", "").strip()
        nums = re.findall(r'\d+', clean_str)
        if not nums:
            return time_str
        val = int(nums[0])
        if 'min' in clean_str or clean_str.endswith('m'):
            return (now - timedelta(minutes=val)).strftime("%Y-%m-%d %H:%M")
        if 'h' in clean_str:
            return (now - timedelta(hours=val)).strftime("%Y-%m-%d %H:%M")
        if 'd' in clean_str or 'dia' in clean_str:
            return (now - timedelta(days=val)).strftime("%Y-%m-%d %H:%M")
        if 'sem' in clean_str or 'w' in clean_str:
            return (now - timedelta(weeks=val)).strftime("%Y-%m-%d %H:%M")
        if 'mes' in clean_str or 'mo' in clean_str:
            return (now - timedelta(days=val * 30)).strftime("%Y-%m-%d %H:%M")
        return time_str
    except Exception:
        return time_str

# ===================== SCRAPER ENGINE =====================

class ScraperEngine:
    """Motor de scraping que corre en un hilo separado."""

    def __init__(self, log_queue, stats_callback):
        self.log_queue = log_queue
        self.stats_callback = stats_callback
        self._running = False
        self._paused = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # No pausado inicialmente
        self._thread = None

        # Stats
        self.stats = {
            "status": "Detenido",
            "cycle": 0,
            "total_posts": 0,
            "new_posts_round": 0,
            "offers_general": 0,
            "offers_structural": 0,
            "emails_found": 0,
            "locations_found": 0,
            "scroll_cycle": 0,
            "next_cycle_in": "",
            "phase": "",
        }

        # Config
        self.wait_minutes = 5
        self.max_scroll = 150
        self.stable_limit = 6

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {msg}")

    def update_stats(self, **kwargs):
        self.stats.update(kwargs)
        self.stats_callback(self.stats.copy())

    @property
    def is_running(self):
        return self._running

    def start(self):
        if self._running:
            return
        self.start_time = time.time()
        self._stop_event.clear()
        self._pause_event.set()
        self._paused = False
        self._running = True
        self._thread = threading.Thread(target=self._run_pipeline, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._pause_event.set()  # Liberar pausa si esta pausado
        self._running = False
        self._paused = False

    def pause(self):
        if not self._running:
            return
        self._paused = True
        self._pause_event.clear()
        self.update_stats(status="Pausado")
        self.log("Pipeline pausado.")

    def resume(self):
        if not self._paused:
            return
        self._paused = False
        self._pause_event.set()
        self.update_stats(status="Ejecutando")
        self.log("Pipeline reanudado.")

    def _check_stop(self):
        return self._stop_event.is_set()

    def _wait_pause(self):
        self._pause_event.wait()

    # --- LinkedIn helpers ---
    def _is_on_login(self, page):
        return "linkedin.com/login" in (page.url or "")

    def _is_on_challenge(self, page):
        u = (page.url or "").lower()
        return "linkedin.com/checkpoint" in u or "challenge" in u

    def _ensure_login(self, page, context):
        email = os.getenv("LINKEDIN_EMAIL")
        password = os.getenv("LINKEDIN_PASSWORD")
        li_at = os.getenv("LINKEDIN_LI_AT")
        
        if li_at and not Path(STATE_FILE).exists():
            context.add_cookies([{"name": "li_at", "value": li_at, "domain": ".www.linkedin.com", "path": "/"}])
            self.log("Usando cookie li_at para sesion automatica (primera sesion).")

        if not email and not password and not li_at:
            raise ValueError("Faltan LINKEDIN_EMAIL/PASSWORD o LINKEDIN_LI_AT en .env")

        try:
            page.goto("https://www.linkedin.com/", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded")
        except Exception as e:
            self.log(f"Advertencia al navegar: {e}")
        page.wait_for_timeout(5000)

        current_url = (page.url or "").lower()
        needs_login = "linkedin.com/login" in current_url or "linkedin.com/uas" in current_url

        if not needs_login:
            username_field = page.locator('input[type="email"], input[autocomplete*="username"], #username, #session_key')
            needs_login = username_field.count() > 0 and username_field.first.is_visible()

        if needs_login:
            self.log("No hay sesion activa -> login automatico...")
            self.update_stats(phase="Login")

            if "linkedin.com/login" not in current_url:
                page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

            if self._is_on_login(page):
                self.log("Rellenando credenciales de usuario...")
                try:
                    page.wait_for_selector('input[type="email"], input[autocomplete*="username"], #username, #session_key', timeout=15000)
                    user_input = page.locator('input[type="email"], input[autocomplete*="username"], #username, #session_key').first
                    pass_input = page.locator('input[type="password"], input[autocomplete*="current-password"], #password, #session_password').first
                    
                    if email and password:
                        user_input.fill(email)
                        pass_input.fill(password)
                        
                        submit_btn = page.locator('button[type="submit"]')
                        if submit_btn.count() > 0:
                            submit_btn.first.click()
                        else:
                            pass_input.press("Enter")
                            
                        page.wait_for_timeout(3000)
                    else:
                        self.log("ERROR: No hay EMAIL o PASSWORD en el .env")
                except Exception as e:
                    self.log(f"Fallo al rellenar login: {e}")

                if self._is_on_challenge(page) or self._is_on_login(page):
                    self.log("!! Challenge/2FA detectado. Resuelvelo en el navegador.")
                    self.update_stats(status="Esperando captcha...")
                    page.wait_for_timeout(60000)
                    retries = 0
                    while (self._is_on_challenge(page) or self._is_on_login(page)) and retries < 12:
                        if self._check_stop():
                            return
                        page.wait_for_timeout(30000)
                        retries += 1

                try:
                    page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                except Exception as e:
                    self.log(f"Advertencia al ir al feed tras login: {e}")
            else:
                self.log("Sesion activa (redireccion al feed).")

            context.storage_state(path=STATE_FILE)
            self.log("Sesion guardada.")
        else:
            self.log("Sesion activa detectada.")

    # --- Extraccion ---
    def _extract_post_data(self, post_locator):
        try:
            text = ""
            text_elem = post_locator.locator('span[data-testid="expandable-text-box"]').first
            if text_elem.count() > 0:
                text = text_elem.inner_text().strip()

            author_name = "Desconocido"
            author_url = ""
            author_links = post_locator.locator("a[href*='/in/'], a[href*='/company/']").all()
            best_link = None
            for link in author_links:
                if len(link.inner_text().strip()) > 2:
                    best_link = link
                    break
            if not best_link and author_links:
                best_link = author_links[0]
            if best_link:
                author_url = best_link.get_attribute("href").split('?')[0]
                name_span = best_link.locator("span[dir='ltr']").first
                if name_span.count() > 0:
                    author_name = name_span.inner_text().strip()
                else:
                    raw_text = best_link.inner_text().strip()
                    author_name = raw_text.split('\n')[0].strip()

            time_abs = ""
            time_elem = post_locator.locator("p, span, div").filter(
                has_text=re.compile(r"^\d+\s*[mhdsy].*\u2022")
            ).first
            if time_elem.count() == 0:
                time_elem = post_locator.locator("text=/\\d+\\s*(min|h|d|sem).*\u2022/i").first
            if time_elem.count() > 0:
                raw_time = time_elem.inner_text().strip()
                if "\u2022" in raw_time:
                    time_part = raw_time.split("\u2022")[0].strip()
                    time_abs = parse_relative_time(time_part)
            if not time_abs:
                post_link = post_locator.locator("a[href*='urn:li:activity'], a[href*='/feed/update/']").first
                if post_link.count() > 0:
                    raw_time = post_link.inner_text().strip().split('\n')[0]
                    time_abs = parse_relative_time(raw_time)

            return {
                "author": author_name,
                "profile_url": author_url,
                "text": text,
                "time_posted": time_abs if time_abs else "No detectado",
                "scraped_at": datetime.now().isoformat()
            }
        except Exception:
            return None

    def _scroll_feed_down(self, page):
        result = page.evaluate("""() => {
            const main = document.querySelector('main');
            if (main && main.scrollHeight > main.clientHeight) {
                const before = main.scrollTop;
                main.scrollTop = main.scrollHeight - main.clientHeight;
                return { container: 'main', before: before, after: main.scrollTop, scrollHeight: main.scrollHeight };
            } else {
                const before = window.scrollY;
                window.scrollTo(0, document.documentElement.scrollHeight - window.innerHeight);
                return { container: 'window', before: before, after: window.scrollY, scrollHeight: document.documentElement.scrollHeight };
            }
        }""")
        page.wait_for_timeout(random.randint(300, 600))
        return result

    def _reached_end(self, page):
        try:
            return page.evaluate("""() => {
                const t = document.body.innerText.toLowerCase();
                return t.includes("you're all caught up") || t.includes("no hay más publicaciones") ||
                       t.includes("estás al día") || t.includes("ya estás al día");
            }""")
        except Exception:
            return False

    # --- FASES ---
    def _phase_scraping(self, page):
        self.log("=== FASE 1: SCRAPING ===")
        self.update_stats(phase="Scraping")

        try:
            page.wait_for_selector("main", timeout=15000)
            page.wait_for_selector('div[role="listitem"]', timeout=10000)
        except PlaywrightTimeout:
            self.log("No se detectaron posts.")
        page.wait_for_timeout(3000)

        all_posts = load_json(EXTRACTED_FILE, [])
        seen_ids = set()
        for p in all_posts:
            if p.get('text'):
                seen_ids.add(f"{p.get('author')}_{p.get('text')[:50]}")

        new_in_round = 0

        locators = page.locator('div[role="listitem"]').all()
        processed_index = 0
        
        for pl in locators:
            data = self._extract_post_data(pl)
            processed_index += 1
            if not data or not data['text']:
                continue
            uid = f"{data['author']}_{data['text'][:50]}"
            if uid not in seen_ids:
                seen_ids.add(uid)
                all_posts.append(data)
                new_in_round += 1
                
        if new_in_round > 0:
            save_json(all_posts, EXTRACTED_FILE)

        last_posts = page.evaluate('() => document.querySelectorAll(\'div[role="listitem"]\').length')
        stable = 0
        phase_start = time.time()
        MAX_PHASE_SECONDS = 480  # 8 minutos máximo por fase de scraping

        for cycle in range(1, self.max_scroll + 1):
            if self._check_stop() or page.is_closed():
                break
            self._wait_pause()

            # Watchdog: si llevamos más de 10 min en esta fase, cortar
            elapsed = time.time() - phase_start
            if elapsed > MAX_PHASE_SECONDS:
                self.log(f"Watchdog: {int(elapsed)}s en scraping. Forzando fin de ciclo para evitar bloqueo.")
                break

            self.update_stats(scroll_cycle=cycle, total_posts=len(all_posts), new_posts_round=new_in_round)

            try:
                # Detección de crash de Chrome (Out of Memory, página muerta, etc.)
                try:
                    page_title = page.title() or ""
                    page_content = page.evaluate('() => document.body ? document.body.innerText.substring(0, 300) : ""') or ""
                except Exception:
                    self.log("⚠️ Página no responde. Intentando recuperar...")
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(3000)
                    except Exception:
                        self.log("❌ No se pudo recuperar la página. Finalizando scraping.")
                        break
                    continue

                crash_indicators = ["¡vaya!", "out of memory", "err_", "no se puede", "aw, snap", "this page isn"]
                combined_text = (page_title + " " + page_content).lower()
                if any(ind in combined_text for ind in crash_indicators):
                    self.log(f"⚠️ Chrome crasheó (detectado en scroll {cycle}). Recargando página...")
                    try:
                        page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(5000)
                        processed_index = 0
                        self.log("✅ Página recuperada. Continuando scraping...")
                    except Exception:
                        self.log("❌ No se pudo recargar LinkedIn. Finalizando scraping.")
                        break
                    continue

                self._scroll_feed_down(page)
                page.wait_for_timeout(random.randint(2500, 4500))

                batch_new = 0
                locators = page.locator('div[role="listitem"]').all()
                
                # Optimización: Solo procesar los posts nuevos
                start_idx = max(0, processed_index - 5)
                
                for pl in locators[start_idx:]:
                    data = self._extract_post_data(pl)
                    if not data or not data['text']:
                        continue
                    uid = f"{data['author']}_{data['text'][:50]}"
                    if uid not in seen_ids:
                        seen_ids.add(uid)
                        all_posts.append(data)
                        batch_new += 1
                        new_in_round += 1
                
                processed_index = len(locators)

                if batch_new > 0:
                    save_json(all_posts, EXTRACTED_FILE)
                    self.log(f"  Scroll {cycle}: +{batch_new} nuevos (Total: {len(all_posts)})")
                    self.update_stats(total_posts=len(all_posts), new_posts_round=new_in_round)
                    
                if processed_index >= 120:
                    self.log(f"Límite seguro de memoria ({processed_index} posts en DOM). Finalizando scraping del ciclo.")
                    break

                if self._reached_end(page):
                    self.log("Fin del feed detectado.")
                    break

                new_count = page.evaluate('() => document.querySelectorAll(\'div[role="listitem"]\').length')
                if new_count > last_posts:
                    last_posts = new_count
                    stable = 0
                else:
                    stable += 1

                if self._is_on_challenge(page):
                    self.log("Challenge detectado. Esperando...")
                    self.update_stats(status="Esperando captcha...")
                    page.wait_for_timeout(60000)
                    if self._is_on_challenge(page):
                        page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded")
                        page.wait_for_timeout(3000)
                    self.update_stats(status="Ejecutando")

                if stable >= self.stable_limit:
                    self.log("Sin contenido nuevo. Fin del scroll.")
                    break

            except TargetClosedError:
                self.log("Pagina cerrada durante scroll.")
                break
            except Exception as e:
                self.log(f"Error scroll {cycle}: {e}")
                # Intentar recuperar en vez de morir
                try:
                    page.reload(wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000)
                    self.log("Página recargada tras error. Continuando...")
                    processed_index = 0
                except Exception:
                    self.log("No se pudo recuperar. Finalizando scraping.")
                    break

        self.log(f"Scraping: +{new_in_round} nuevos. Total: {len(all_posts)}")
        self.update_stats(total_posts=len(all_posts), new_posts_round=new_in_round)
        return len(all_posts)

    def _phase_locations(self):
        if self._check_stop():
            return
        self.log("=== FASE 2: UBICACIONES ===")
        self.update_stats(phase="Ubicaciones")

        posts = load_json(EXTRACTED_FILE, [])
        localidades = load_json(LOCALIDADES_FILE, {"regions": []})

        count = 0
        for post in posts:
            regions, communes = find_locations_in_text(post['text'], localidades)
            post['locations'] = {'regions': regions, 'communes': communes}
            if regions or communes:
                count += 1

        save_json(posts, LOCATIONS_FILE)
        self.log(f"Ubicaciones: {count}/{len(posts)} geolocalizados.")
        self.update_stats(locations_found=count)

    def _phase_detection(self):
        if self._check_stop():
            return
        self.log("=== FASE 3: DETECCION ===")
        self.update_stats(phase="Deteccion")

        posts = load_json(LOCATIONS_FILE, [])
        keywords = load_json(KEYWORDS_FILE, {"positive": [], "negative": []})
        training = load_json(TRAINING_FILE, [])

        vote_map = {}
        for item in training:
            key = f"{item.get('author', '')}|{item.get('text', '')[:50]}"
            vote_map[key] = item.get('is_offer')

        # Cargar contactos para cruce
        contacts = load_contacts()

        offers = 0
        structural = 0
        emails_total = 0
        from_contacts = 0
        spam_filtered = 0

        for post in posts:
            author = post.get('author', '')
            key = f"{author}|{post.get('text', '')[:50]}"
            result = detect_job_offer(post['text'], keywords, vote_map.get(key))

            # Cruce con contactos
            contact_match = match_author(author)
            if contact_match:
                post['is_contact'] = True
                post['contact_info'] = contact_match
            else:
                post['is_contact'] = False
                post['contact_info'] = None

            # Filtro de spam: penalizar autores que son asesores/vendedores
            is_spam, spam_role = is_spam_author(author)
            if is_spam:
                result['is_offer'] = False
                result['score'] = 0.01
                result['spam_filtered'] = True
                result['spam_reason'] = spam_role
                spam_filtered += 1
            else:
                result['spam_filtered'] = False

            post['job_prediction'] = result
            if result['is_offer']:
                offers += 1
                if post.get('is_contact'):
                    from_contacts += 1
            if result.get('is_structural', False):
                structural += 1
            emails_total += len(result.get('emails', []))

        save_json(posts, LOCATIONS_FILE)
        contact_msg = f" | De contactos: {from_contacts}" if from_contacts > 0 else ""
        spam_msg = f" | Spam filtrado: {spam_filtered}" if spam_filtered > 0 else ""
        self.log(f"Ofertas: {offers} | Estructurales: {structural} | Correos: {emails_total}{contact_msg}{spam_msg}")
        self.update_stats(offers_general=offers, offers_structural=structural, emails_found=emails_total)

    def _phase_export(self):
        if self._check_stop():
            return
        self.log("=== FASE 4: EXPORTACION ===")
        self.update_stats(phase="Exportacion")

        posts = load_json(LOCATIONS_FILE, [])
        structural_offers = []
        all_offers = []

        for post in posts:
            pred = post.get('job_prediction', {})
            if not pred.get('is_offer', False):
                continue
            if pred.get('spam_filtered', False):
                continue
            emails_str = ", ".join(pred.get('emails', []))
            locs = post.get('locations', {})
            regions = ", ".join(locs.get('regions', []))
            communes = ", ".join([c['commune'] for c in locs.get('communes', [])])

            # Info de contacto
            contact_info = post.get('contact_info') or {}
            es_contacto = 'Sí' if post.get('is_contact') else 'No'
            contacto_empresa = contact_info.get('company', '') if contact_info else ''
            contacto_cargo = contact_info.get('position', '') if contact_info else ''

            row = {
                'Autor': post.get('author', ''),
                'Es Contacto': es_contacto,
                'Empresa Contacto': contacto_empresa,
                'Cargo Contacto': contacto_cargo,
                'URL Perfil': post.get('profile_url', ''),
                'Correos': emails_str,
                'Region': regions,
                'Comuna': communes,
                'Fecha': post.get('time_posted', ''),
                'Score': pred.get('score', 0),
                'IA Validado': 'Sí' if pred.get('ai_verified', False) else 'No',
                'Rol': pred.get('role', ''),
                'Empresa': pred.get('company', ''),
                'Texto': post.get('text', '').replace('\n', ' ')[:500]
            }
            all_offers.append(row)
            if pred.get('is_structural', False):
                structural_offers.append(row)

        fieldnames = ['Autor', 'Es Contacto', 'Empresa Contacto', 'Cargo Contacto', 'URL Perfil', 'Correos', 'Region', 'Comuna', 'Fecha', 'Score', 'IA Validado', 'Rol', 'Empresa', 'Texto']
        if all_offers:
            try:
                with open(ALL_OFFERS_CSV, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_offers)
                self.log(f"Exportado: {len(all_offers)} ofertas -> {ALL_OFFERS_CSV}")
            except (PermissionError, OSError) as e:
                self.log(f"ERROR: No se pudo escribir {ALL_OFFERS_CSV} (¿esta abierto en Excel?): {e}")
        if structural_offers:
            try:
                with open(STRUCTURAL_CSV, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(structural_offers)
                self.log(f"Exportado: {len(structural_offers)} estructurales -> {STRUCTURAL_CSV}")
            except (PermissionError, OSError) as e:
                self.log(f"ERROR: No se pudo escribir {STRUCTURAL_CSV} (¿esta abierto en Excel?): {e}")

    def _phase_networking(self, page):
        if self._check_stop():
            return
        self.log("=== FASE 5: NETWORKING (AUTOCONNECT) ===")
        self.update_stats(phase="Networking")
        
        net_stats = load_json(NETWORK_STATS_FILE, {"followers": 0, "weekly_invites": 0, "week_start": str(datetime.now().date())})
        
        try:
            week_start = datetime.strptime(net_stats.get("week_start", str(datetime.now().date())), "%Y-%m-%d").date()
        except Exception:
            week_start = datetime.now().date()
            
        if (datetime.now().date() - week_start).days >= 7:
            self.log("Semana completada, reiniciando contador de invitaciones.")
            net_stats["weekly_invites"] = 0
            net_stats["week_start"] = str(datetime.now().date())
            
        max_weekly = 100
        if net_stats["weekly_invites"] >= max_weekly:
            self.log(f"Límite semanal alcanzado ({net_stats['weekly_invites']}/{max_weekly}). Omitiendo invitaciones.")
            page.goto(LINKEDIN_NETWORK_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
        else:
            self.log("Navegando a Mi red...")
            page.goto(LINKEDIN_NETWORK_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            
            try:
                # Botones de conectar
                buttons = page.locator("button:has-text('Conectar'), button:has-text('Connect')").all()
                to_invite = min(random.randint(2, 5), max_weekly - net_stats["weekly_invites"], len(buttons))
                
                if to_invite > 0:
                    self.log(f"Encontrados {len(buttons)} botones de conexión. Enviando {to_invite} invitaciones...")
                    invited = 0
                    for btn in buttons[:to_invite]:
                        if self._check_stop():
                            break
                        try:
                            btn.scroll_into_view_if_needed()
                            page.wait_for_timeout(500)
                            btn.click()
                            page.wait_for_timeout(random.randint(1500, 3000))
                            invited += 1
                        except Exception as e:
                            self.log(f"No se pudo hacer click en Conectar: {e}")
                    
                    net_stats["weekly_invites"] += invited
                    self.log(f"+{invited} invitaciones enviadas. Total semana: {net_stats['weekly_invites']}/{max_weekly}")
            except Exception as e:
                self.log(f"Error buscando botones de Conectar: {e}")

        try:
            followers_text = page.locator("text=seguidor").first.text_content(timeout=2000)
            if followers_text:
                nums = re.findall(r'[\d\.]+', followers_text)
                if nums:
                    net_stats["followers"] = nums[0].replace('.', '')
        except Exception:
            pass
            
        save_json(net_stats, NETWORK_STATS_FILE)
        self.update_stats(
            followers=net_stats.get("followers", 0), 
            weekly_invites=f"{net_stats.get('weekly_invites', 0)}/{max_weekly}"
        )

    # --- PIPELINE PRINCIPAL ---
    def _run_pipeline(self):
        load_env(ENV_FILE)
        
        while not self._check_stop():
            self.update_stats(status="Iniciando navegador...")
            self.log("Iniciando navegador...")
            try:
                with sync_playwright() as p:
                    try:
                        browser = p.chromium.launch(
                            headless=False, slow_mo=30, channel="chrome",
                            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
                        )
                    except Exception:
                        try:
                            browser = p.chromium.launch(
                                headless=False, slow_mo=30, channel="msedge",
                                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
                            )
                        except Exception:
                            browser = p.chromium.launch(
                                headless=False, slow_mo=30,
                                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
                            )
                    
                    ctx_opts = {
                        "no_viewport": True,
                        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    }
                    if Path(STATE_FILE).exists():
                        context = browser.new_context(storage_state=STATE_FILE, **ctx_opts)
                    else:
                        context = browser.new_context(**ctx_opts)

                    page = context.new_page()
                    page.set_default_timeout(15000)  # 15s max para cualquier operación de Playwright
                    page.set_default_navigation_timeout(30000)  # 30s max para navegación

                    try:
                        self._ensure_login(page, context)
                        if self._check_stop():
                            break

                        while not self._check_stop():
                            self._wait_pause()
                            if self._check_stop():
                                break

                            self.stats["cycle"] += 1
                            cycle = self.stats["cycle"]
                            self.update_stats(status="Ejecutando", phase="Inicio ciclo")
                            self.log(f"--- CICLO #{cycle} - {datetime.now().strftime('%H:%M:%S')} ---")

                            if cycle > 1:
                                self.log("Refrescando feed...")
                                self.update_stats(phase="Refrescando")
                                page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded")
                                page.wait_for_timeout(3000)

                            self._phase_scraping(page)
                            if self._check_stop():
                                break

                            try:
                                context.storage_state(path=STATE_FILE)
                            except Exception:
                                pass

                            self._phase_locations()
                            self._phase_detection()
                            self._phase_export()
                            self._phase_networking(page)

                            if self._check_stop():
                                break

                            self.log(f"Ciclo #{cycle} completado. Esperando {self.wait_minutes} min...")
                            self.update_stats(status="Esperando", phase="Espera entre ciclos")

                            wait_secs = self.wait_minutes * 60
                            for remaining in range(wait_secs, 0, -1):
                                if self._check_stop():
                                    break
                                self._wait_pause()
                                if remaining % 30 == 0:
                                    mins = remaining // 60
                                    secs = remaining % 60
                                    self.update_stats(next_cycle_in=f"{mins}m {secs}s")
                                time.sleep(1)

                            self.update_stats(next_cycle_in="")

                    except Exception as e:
                        self.log(f"Error en navegador: {type(e).__name__}: {e}")
                        if not self._check_stop():
                            self.log("Reiniciando en 10 segundos debido al error...")
                            time.sleep(10)
                    finally:
                        try:
                            context.storage_state(path=STATE_FILE)
                        except Exception:
                            pass
                        try:
                            if not page.is_closed():
                                context.close()
                        except Exception:
                            pass
                        try:
                            browser.close()
                        except Exception:
                            pass

            except Exception as e:
                self.log(f"Error fatal: {e}")
                if not self._check_stop():
                    time.sleep(10)
                    
        # Fin de la ejecucion
        self._running = False
        self._paused = False
        self.update_stats(status="Detenido", phase="")
        self.log("Pipeline detenido.")


# ===================== INTERFAZ TKINTER =====================

class DashboardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LinkedIn Scraper - Panel de Control")
        self.root.geometry("980x720")
        self.root.minsize(860, 600)
        self.root.configure(bg=COLORS["bg"])

        # Estilo ttk
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self._configure_styles()

        # Cola de logs
        self.log_queue = queue.Queue()

        # Motor
        self.engine = ScraperEngine(self.log_queue, self._on_stats_update)

        # Variables
        self.var_status = StringVar(value="Detenido")
        self.var_cycle = StringVar(value="0")
        self.var_total_posts = StringVar(value="0")
        self.var_new_posts = StringVar(value="0")
        self.var_offers = StringVar(value="0")
        self.var_structural = StringVar(value="0")
        self.var_emails = StringVar(value="0")
        self.var_locations = StringVar(value="0")
        self.var_followers = StringVar(value="0")
        self.var_weekly_invites = StringVar(value="0/100")
        self.var_scroll = StringVar(value="0")
        self.var_next = StringVar(value="-")
        self.var_phase = StringVar(value="-")
        self.var_elapsed = StringVar(value="00:00:00")
        self.var_wait = IntVar(value=5)
        self.var_max_scroll = IntVar(value=150)

        # Construir UI
        self._build_header()
        self._build_stats()
        self._build_controls()
        self._build_log()

        # Iniciar actualizaciones
        self._update_logs()
        self._update_timer()

        # Cargar stats iniciales
        self._load_initial_stats()

        # Cerrar bien
        self.root.protocol("WM_DELETE_CLOSE", self._on_close)

    def _configure_styles(self):
        s = self.style
        s.configure("Dark.TFrame", background=COLORS["bg"])
        s.configure("Card.TFrame", background=COLORS["bg_card"])
        s.configure("Header.TLabel", background=COLORS["bg"], foreground=COLORS["text_bright"],
                     font=("Segoe UI", 18, "bold"))
        s.configure("SubHeader.TLabel", background=COLORS["bg"], foreground=COLORS["text_dim"],
                     font=("Segoe UI", 10))
        s.configure("StatTitle.TLabel", background=COLORS["bg_card"], foreground=COLORS["text_dim"],
                     font=("Segoe UI", 9))
        s.configure("StatValue.TLabel", background=COLORS["bg_card"], foreground=COLORS["text_bright"],
                     font=("Segoe UI", 20, "bold"))
        s.configure("Phase.TLabel", background=COLORS["bg"], foreground=COLORS["accent_yellow"],
                     font=("Segoe UI", 10, "italic"))
        s.configure("Status.TLabel", background=COLORS["bg"], foreground=COLORS["accent_green"],
                     font=("Segoe UI", 12, "bold"))
        s.configure("Config.TLabel", background=COLORS["bg"], foreground=COLORS["text"],
                     font=("Segoe UI", 10))

        # Buttons
        s.configure("Start.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 8))
        s.configure("Stop.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 8))
        s.configure("Pause.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 8))

        # Spinbox
        s.configure("TSpinbox", fieldbackground=COLORS["bg_input"], foreground=COLORS["text_bright"])

    def _build_header(self):
        hdr = Frame(self.root, bg=COLORS["bg"], pady=12, padx=20)
        hdr.pack(fill=X)

        title = Label(hdr, text="LinkedIn Scraper", font=("Segoe UI", 20, "bold"),
                      bg=COLORS["bg"], fg=COLORS["text_bright"])
        title.pack(side=LEFT)

        # Status badge
        status_frame = Frame(hdr, bg=COLORS["bg"])
        status_frame.pack(side=RIGHT)

        self.status_dot = Label(status_frame, text="\u25cf", font=("Segoe UI", 14),
                                bg=COLORS["bg"], fg=COLORS["stopped"])
        self.status_dot.pack(side=LEFT, padx=(0, 6))

        self.status_label = Label(status_frame, textvariable=self.var_status,
                                  font=("Segoe UI", 12, "bold"), bg=COLORS["bg"], fg=COLORS["text"])
        self.status_label.pack(side=LEFT)

        # Phase
        phase_label = Label(hdr, textvariable=self.var_phase, font=("Segoe UI", 10, "italic"),
                           bg=COLORS["bg"], fg=COLORS["accent_yellow"])
        phase_label.pack(side=RIGHT, padx=(0, 20))

    def _build_stats(self):
        container = Frame(self.root, bg=COLORS["bg"], padx=20, pady=4)
        container.pack(fill=X)

        stats_data = [
            ("Ciclo", self.var_cycle, COLORS["accent_blue"], None),
            ("Posts Totales", self.var_total_posts, COLORS["text_bright"], None),
            ("Nuevos (ronda)", self.var_new_posts, COLORS["accent_green"], None),
            ("Ofertas", self.var_offers, COLORS["accent_yellow"], "Todas_Ofertas.csv"),
            ("Estructurales", self.var_structural, COLORS["accent"], "Ofertas_Estructurales.csv"),
            ("Correos", self.var_emails, COLORS["success"], "Todas_Ofertas.csv"),
            ("Geolocalizados", self.var_locations, COLORS["accent_blue"], None),
            ("Seguidores", self.var_followers, COLORS["text_bright"], None),
            ("Invitaciones", self.var_weekly_invites, COLORS["accent_green"], None),
        ]

        for i, (title, var, color, csv_file) in enumerate(stats_data):
            # Change cursor to hand if clickable
            cursor = "hand2" if csv_file else ""
            card = Frame(container, bg=COLORS["bg_card"], padx=12, pady=8,
                        highlightbackground=COLORS["border"], highlightthickness=1,
                        cursor=cursor)
            card.pack(side=LEFT, fill=X, expand=True, padx=3)

            lbl_title = Label(card, text=title, font=("Segoe UI", 8), bg=COLORS["bg_card"],
                             fg=COLORS["text_dim"], cursor=cursor)
            lbl_title.pack()

            lbl_val = Label(card, textvariable=var, font=("Segoe UI", 18, "bold"),
                           bg=COLORS["bg_card"], fg=color, cursor=cursor)
            lbl_val.pack()

            if csv_file:
                # Bind click event
                def make_click_handler(c_file=csv_file, t=title):
                    return lambda e: self._show_data_viewer(t, c_file)
                handler = make_click_handler()
                card.bind("<Button-1>", handler)
                lbl_title.bind("<Button-1>", handler)
                lbl_val.bind("<Button-1>", handler)

    def _build_controls(self):
        ctrl = Frame(self.root, bg=COLORS["bg"], padx=20, pady=10)
        ctrl.pack(fill=X)

        # Botones
        btn_frame = Frame(ctrl, bg=COLORS["bg"])
        btn_frame.pack(side=LEFT)

        self.btn_start = Button(btn_frame, text="\u25b6  INICIAR", font=("Segoe UI", 11, "bold"),
                                bg="#00c853", fg="white", activebackground="#00e676",
                                relief="flat", padx=18, pady=6, cursor="hand2",
                                command=self._on_start)
        self.btn_start.pack(side=LEFT, padx=3)

        self.btn_pause = Button(btn_frame, text="\u275a\u275a  PAUSAR", font=("Segoe UI", 11, "bold"),
                                bg="#ffd600", fg="#1a1a2e", activebackground="#ffab00",
                                relief="flat", padx=18, pady=6, cursor="hand2",
                                command=self._on_pause, state=DISABLED)
        self.btn_pause.pack(side=LEFT, padx=3)

        self.btn_stop = Button(btn_frame, text="\u25a0  DETENER", font=("Segoe UI", 11, "bold"),
                               bg="#ff1744", fg="white", activebackground="#ff5252",
                               relief="flat", padx=18, pady=6, cursor="hand2",
                               command=self._on_stop, state=DISABLED)
        self.btn_stop.pack(side=LEFT, padx=3)
        
        self.btn_train = Button(btn_frame, text="🧠 ENTRENAR BOT", font=("Segoe UI", 11, "bold"),
                               bg="#9c27b0", fg="white", activebackground="#ba68c8",
                               relief="flat", padx=18, pady=6, cursor="hand2",
                               command=self._open_training_window)
        self.btn_train.pack(side=LEFT, padx=3)

        # Separador
        Frame(ctrl, bg=COLORS["border"], width=2).pack(side=LEFT, fill=Y, padx=14)

        # Config
        cfg_frame = Frame(ctrl, bg=COLORS["bg"])
        cfg_frame.pack(side=LEFT)

        Label(cfg_frame, text="Espera (min):", font=("Segoe UI", 10),
              bg=COLORS["bg"], fg=COLORS["text"]).pack(side=LEFT, padx=(0, 4))
        self.spin_wait = ttk.Spinbox(cfg_frame, from_=1, to=60, width=4,
                                     textvariable=self.var_wait, font=("Segoe UI", 10))
        self.spin_wait.pack(side=LEFT, padx=(0, 14))

        Label(cfg_frame, text="Max scroll:", font=("Segoe UI", 10),
              bg=COLORS["bg"], fg=COLORS["text"]).pack(side=LEFT, padx=(0, 4))
        self.spin_scroll = ttk.Spinbox(cfg_frame, from_=10, to=500, width=5,
                                       textvariable=self.var_max_scroll, font=("Segoe UI", 10))
        self.spin_scroll.pack(side=LEFT)

        # Proximo ciclo y Tiempo
        next_frame = Frame(ctrl, bg=COLORS["bg"])
        next_frame.pack(side=LEFT, padx=20)
        
        Label(next_frame, text="Tiempo activo:", font=("Segoe UI", 9),
              bg=COLORS["bg"], fg=COLORS["text_dim"]).pack(side=LEFT, padx=(0, 4))
        Label(next_frame, textvariable=self.var_elapsed, font=("Segoe UI", 11, "bold"),
              bg=COLORS["bg"], fg=COLORS["accent_green"]).pack(side=LEFT)
              
        Label(next_frame, text=" | Proximo ciclo:", font=("Segoe UI", 9),
              bg=COLORS["bg"], fg=COLORS["text_dim"]).pack(side=LEFT, padx=(10, 4))
        Label(next_frame, textvariable=self.var_next, font=("Segoe UI", 11, "bold"),
              bg=COLORS["bg"], fg=COLORS["accent_blue"]).pack(side=LEFT)

    def _build_log(self):
        log_frame = Frame(self.root, bg=COLORS["bg"], padx=20, pady=6)
        log_frame.pack(fill=BOTH, expand=True)

        Label(log_frame, text="Log de Actividad", font=("Segoe UI", 10, "bold"),
              bg=COLORS["bg"], fg=COLORS["text_dim"]).pack(anchor=W, pady=(0, 4))

        text_frame = Frame(log_frame, bg=COLORS["bg_card"],
                          highlightbackground=COLORS["border"], highlightthickness=1)
        text_frame.pack(fill=BOTH, expand=True)

        scrollbar = Scrollbar(text_frame)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.log_text = Text(text_frame, bg="#0d1117", fg=COLORS["text"],
                            font=("Cascadia Code", 9), wrap=WORD,
                            yscrollcommand=scrollbar.set, state=DISABLED,
                            insertbackground=COLORS["text"], selectbackground=COLORS["accent_blue"],
                            padx=10, pady=6, relief="flat", borderwidth=0)
        self.log_text.pack(fill=BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

        # Tags para colores en el log
        self.log_text.tag_configure("phase", foreground=COLORS["accent_yellow"])
        self.log_text.tag_configure("success", foreground=COLORS["success"])
        self.log_text.tag_configure("error", foreground=COLORS["error"])
        self.log_text.tag_configure("info", foreground=COLORS["accent_blue"])

    # --- Event handlers ---
    def _update_timer(self):
        if self.engine.is_running and hasattr(self.engine, 'start_time'):
            elapsed = int(time.time() - self.engine.start_time)
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            self.var_elapsed.set(f"{h:02d}:{m:02d}:{s:02d}")
        elif not self.engine.is_running:
            self.var_elapsed.set("00:00:00")
        self.root.after(1000, self._update_timer)

    def _on_start(self):
        self.engine.wait_minutes = self.var_wait.get()
        self.engine.max_scroll = self.var_max_scroll.get()
        self.engine.stats["cycle"] = 0
        self.engine.start()

        self.btn_start.config(state=DISABLED)
        self.btn_pause.config(state=NORMAL)
        self.btn_stop.config(state=NORMAL)
        self.spin_wait.config(state=DISABLED)
        self.spin_scroll.config(state=DISABLED)

        self._append_log("[SISTEMA] Pipeline iniciado.\n", "success")

    def _on_pause(self):
        if self.engine._paused:
            self.engine.resume()
            self.btn_pause.config(text="\u275a\u275a  PAUSAR", bg="#ffd600", fg="#1a1a2e")
        else:
            self.engine.pause()
            self.btn_pause.config(text="\u25b6  REANUDAR", bg="#448aff", fg="white")

    def _on_stop(self):
        self.engine.stop()
        self.btn_start.config(state=NORMAL)
        self.btn_pause.config(state=DISABLED, text="\u275a\u275a  PAUSAR", bg="#ffd600", fg="#1a1a2e")
        self.btn_stop.config(state=DISABLED)
        self.spin_wait.config(state=NORMAL)
        self.spin_scroll.config(state=NORMAL)
        self._append_log("[SISTEMA] Deteniendo pipeline...\n", "error")

    def _on_close(self):
        if self.engine.is_running:
            self.engine.stop()
            time.sleep(1)
        self.root.destroy()

    def _show_data_viewer(self, title, csv_file):
        if not Path(csv_file).exists():
            messagebox.showinfo("Aviso", f"El archivo aún no ha sido generado.\nPor favor, espera a que el bot termine la fase de Scraping actual (ciclo en progreso) para que analice y genere este reporte.")
            return
        DataViewer(self.root, title, csv_file)

    def _open_training_window(self):
        FeedbackWindow(self.root)

    # --- Actualizaciones ---
    def _on_stats_update(self, stats):
        # Llamado desde el hilo del engine, programar en el hilo principal
        self.root.after(0, self._apply_stats, stats)

    def _apply_stats(self, stats):
        self.var_status.set(stats.get("status", ""))
        self.var_cycle.set(str(stats.get("cycle", 0)))
        self.var_total_posts.set(str(stats.get("total_posts", 0)))
        self.var_new_posts.set(str(stats.get("new_posts_round", 0)))
        self.var_offers.set(str(stats.get("offers_general", 0)))
        self.var_structural.set(str(stats.get("offers_structural", 0)))
        self.var_emails.set(str(stats.get("emails_found", 0)))
        self.var_locations.set(str(stats.get("locations_found", 0)))
        if "followers" in stats:
            self.var_followers.set(str(stats.get("followers", 0)))
        if "weekly_invites" in stats:
            self.var_weekly_invites.set(str(stats.get("weekly_invites", "0/100")))
        self.var_next.set(stats.get("next_cycle_in", "-") or "-")
        self.var_phase.set(stats.get("phase", "") or "")

        status = stats.get("status", "")
        if "Ejecutando" in status or "Iniciando" in status:
            self.status_dot.config(fg=COLORS["running"])
        elif "Esperando" in status or "Pausado" in status:
            self.status_dot.config(fg=COLORS["waiting"])
        else:
            self.status_dot.config(fg=COLORS["stopped"])

        # Re-enable start when stopped
        if status == "Detenido":
            self.btn_start.config(state=NORMAL)
            self.btn_pause.config(state=DISABLED)
            self.btn_stop.config(state=DISABLED)
            self.spin_wait.config(state=NORMAL)
            self.spin_scroll.config(state=NORMAL)

    def _update_logs(self):
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                tag = None
                if "FASE" in msg or "===" in msg:
                    tag = "phase"
                elif "Error" in msg or "!!" in msg:
                    tag = "error"
                elif "completado" in msg or "Exportado" in msg or "guardada" in msg:
                    tag = "success"
                self._append_log(msg + "\n", tag)
            except queue.Empty:
                break
        self.root.after(200, self._update_logs)

    def _append_log(self, msg, tag=None):
        self.log_text.config(state=NORMAL)
        if tag:
            self.log_text.insert(END, msg, tag)
        else:
            self.log_text.insert(END, msg)
        self.log_text.see(END)
        self.log_text.config(state=DISABLED)

    def _load_initial_stats(self):
        posts = load_json(LOCATIONS_FILE, [])
        if not posts:
            posts = load_json(EXTRACTED_FILE, [])
        
        self.var_total_posts.set(str(len(posts)))
        
        offers = 0
        structural = 0
        emails_total = 0
        locations = 0

        for post in posts:
            pred = post.get('job_prediction', {})
            if pred.get('is_offer'):
                offers += 1
            if pred.get('is_structural'):
                structural += 1
            emails_total += len(pred.get('emails', []))
            locs = post.get('locations', {})
            if locs.get('regions') or locs.get('communes'):
                locations += 1

        self.var_offers.set(str(offers))
        self.var_structural.set(str(structural))
        self.var_emails.set(str(emails_total))
        self.var_locations.set(str(locations))
        
        net_stats = load_json(NETWORK_STATS_FILE, {"followers": 0, "weekly_invites": 0})
        self.var_followers.set(str(net_stats.get("followers", 0)))
        self.var_weekly_invites.set(f"{net_stats.get('weekly_invites', 0)}/100")
        
        self._append_log(f"[SISTEMA] Panel de control listo. {len(posts)} posts en base de datos.\n", "info")


# ===================== VISOR DE DATOS =====================

class DataViewer:
    def __init__(self, parent, title, csv_file):
        top = Toplevel(parent)
        top.title(f"Visor de Datos - {title}")
        top.geometry("1100x600")
        top.configure(bg=COLORS["bg"])

        Label(top, text=f"Datos: {title}", font=("Segoe UI", 16, "bold"),
              bg=COLORS["bg"], fg=COLORS["text_bright"]).pack(pady=10)

        frame = Frame(top, bg=COLORS["bg_card"])
        frame.pack(fill=BOTH, expand=True, padx=20, pady=10)

        # Scrollbars
        scroll_y = Scrollbar(frame, orient=VERTICAL)
        scroll_y.pack(side=RIGHT, fill=Y)
        scroll_x = Scrollbar(frame, orient=HORIZONTAL)
        scroll_x.pack(side=BOTTOM, fill=X)

        tree = ttk.Treeview(frame, yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)

        scroll_y.config(command=tree.yview)
        scroll_x.config(command=tree.xview)

        # Style treeview for dark theme
        s = ttk.Style()
        s.configure("Treeview", background="#0d1117", foreground=COLORS["text_bright"],
                             fieldbackground="#0d1117", rowheight=30)
        s.map("Treeview", background=[("selected", COLORS["accent_blue"])])

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                headers = next(reader)
                
                tree["columns"] = headers
                tree["show"] = "headings"
                
                for h in headers:
                    tree.heading(h, text=h)
                    tree.column(h, width=150, anchor=W)
                
                # Expand "Texto" column if exists
                if "Texto" in headers:
                    tree.column("Texto", width=500)
                
                # Encontrar el indice de la columna "Correos"
                correos_idx = headers.index("Correos") if "Correos" in headers else -1

                for row in reader:
                    # Clean newlines from text for better display
                    clean_row = [str(cell).replace('\\n', ' ') for cell in row]
                    
                    # Si el titulo es "Correos", filtrar solo los que tienen correos
                    if title == "Correos" and correos_idx != -1:
                        if not clean_row[correos_idx].strip():
                            continue
                            
                    tree.insert("", END, values=clean_row)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar {csv_file}\n{e}")

# ===================== MÓDULO DE FEEDBACK (ENTRENAMIENTO) =====================

class FeedbackWindow:
    def __init__(self, parent):
        self.top = Toplevel(parent)
        self.top.title("Tinder de Empleos - Entrenamiento")
        self.top.geometry("800x600")
        self.top.configure(bg=COLORS["bg"])
        self.top.grab_set()

        self.posts_to_review = []
        self.current_idx = 0
        self.training_data = []

        self._load_data()
        self._build_ui()
        self._show_post()

        self.top.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_data(self):
        # Cargar posts extraidos
        extracted = load_json(LOCATIONS_FILE, [])
        # Cargar datos de entrenamiento
        self.training_data = load_json(TRAINING_FILE, [])

        # Crear conjunto de posts ya votados para ignorarlos
        voted_keys = set()
        for t in self.training_data:
            key = f"{t.get('author', '')}|{t.get('text', '')[:50]}"
            voted_keys.add(key)

        # Filtrar posts que no tienen voto
        for p in extracted:
            key = f"{p.get('author', '')}|{p.get('text', '')[:50]}"
            if key not in voted_keys:
                self.posts_to_review.append(p)

    def _build_ui(self):
        hdr = Frame(self.top, bg=COLORS["bg"], pady=10)
        hdr.pack(fill=X)
        self.lbl_counter = Label(hdr, text="", font=("Segoe UI", 12), bg=COLORS["bg"], fg=COLORS["text_dim"])
        self.lbl_counter.pack()

        # Text area
        text_frame = Frame(self.top, bg=COLORS["bg_card"], padx=20, pady=20)
        text_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)

        self.lbl_author = Label(text_frame, text="", font=("Segoe UI", 14, "bold"), bg=COLORS["bg_card"], fg=COLORS["accent_blue"])
        self.lbl_author.pack(anchor=W)

        self.txt_content = Text(text_frame, font=("Segoe UI", 12), bg=COLORS["bg_card"], fg=COLORS["text_bright"], 
                                wrap=WORD, relief="flat", height=15)
        self.txt_content.pack(fill=BOTH, expand=True, pady=(10, 0))
        self.txt_content.config(state=DISABLED)

        # Botones
        btn_frame = Frame(self.top, bg=COLORS["bg"], pady=20)
        btn_frame.pack(fill=X)

        btn_no = Button(btn_frame, text="❌ NO ES OFERTA", font=("Segoe UI", 14, "bold"),
                        bg="#ff1744", fg="white", activebackground="#ff5252",
                        padx=30, pady=15, cursor="hand2", command=lambda: self._vote(False))
        btn_no.pack(side=LEFT, expand=True)

        btn_yes = Button(btn_frame, text="✅ SÍ ES OFERTA", font=("Segoe UI", 14, "bold"),
                         bg="#00c853", fg="white", activebackground="#00e676",
                         padx=30, pady=15, cursor="hand2", command=lambda: self._vote(True))
        btn_yes.pack(side=RIGHT, expand=True)

    def _show_post(self):
        if self.current_idx >= len(self.posts_to_review):
            self.lbl_counter.config(text="¡Felicidades! No hay más posts por revisar.")
            self.lbl_author.config(text="Fin de la revisión")
            self.txt_content.config(state=NORMAL)
            self.txt_content.delete("1.0", END)
            self.txt_content.insert(END, "Has revisado todos los posts nuevos.\nPuedes cerrar esta ventana para que el bot empiece a aprender de tus respuestas.")
            self.txt_content.config(state=DISABLED)
            return

        post = self.posts_to_review[self.current_idx]
        total = len(self.posts_to_review)
        self.lbl_counter.config(text=f"Revisando {self.current_idx + 1} de {total}")
        
        self.lbl_author.config(text=post.get('author', 'Autor Desconocido'))
        
        self.txt_content.config(state=NORMAL)
        self.txt_content.delete("1.0", END)
        self.txt_content.insert(END, post.get('text', ''))
        self.txt_content.config(state=DISABLED)

    def _vote(self, is_offer):
        if self.current_idx >= len(self.posts_to_review):
            return

        post = self.posts_to_review[self.current_idx]
        
        # Formato de training_data
        vote_entry = {
            "author": post.get("author", ""),
            "text": post.get("text", ""),
            "is_offer": is_offer,
            "votes": {
                "yes": 1 if is_offer else 0,
                "no": 1 if not is_offer else 0
            }
        }
        self.training_data.append(vote_entry)
        
        # Avanzar
        self.current_idx += 1
        self._show_post()

    def _on_close(self):
        # Guardar si hubieron cambios
        save_json(self.training_data, TRAINING_FILE)
        
        # Llamar silenciosamente a train_model
        try:
            print("[FEEDBACK] Iniciando auto-entrenamiento con nuevas respuestas...")
            train_model.train()
            print("[FEEDBACK] Auto-entrenamiento completado con éxito.")
        except Exception as e:
            print(f"[FEEDBACK] Error al entrenar: {e}")
            
        self.top.destroy()


# ===================== MAIN =====================

def main():
    import sys
    autostart = "--autostart" in sys.argv
    root = Tk()
    app = DashboardApp(root)
    if autostart:
        root.after(1000, app._on_start)
    root.mainloop()

if __name__ == "__main__":
    main()
