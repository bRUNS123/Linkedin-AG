import os
import random
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError
from playwright._impl._errors import TargetClosedError

STATE_FILE = "linkedin_state.json"
ENV_FILE = ".env"

LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"

# ✅ SELECTORES ACTUALIZADOS PARA LINKEDIN 2025
POST_SELECTORS = [
    'div[role="listitem"]',
    'div[data-view-name="feed-full-update"]',
    'div[componentkey*="FeedType_MAIN_FEED"]',
]

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

def print_status(msg):
    print(msg, flush=True)

def is_on_login(page) -> bool:
    return "linkedin.com/login" in (page.url or "")

def is_on_challenge(page) -> bool:
    u = (page.url or "").lower()
    return "linkedin.com/checkpoint" in u or "challenge" in u

def ensure_login(page, context):
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    if not email or not password:
        raise ValueError("Faltan LINKEDIN_EMAIL o LINKEDIN_PASSWORD en tu .env")

    page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)

    if is_on_login(page):
        print_status("🔐 No hay sesión activa → login automático (.env) ...")
        page.goto(LINKEDIN_LOGIN_URL, wait_until="domcontentloaded")

        page.wait_for_selector("#username", timeout=15000)
        page.fill("#username", email)
        page.fill("#password", password)
        page.click("button[type='submit']")

        page.wait_for_timeout(2500)

        if is_on_challenge(page) or is_on_login(page):
            print_status("⚠️ LinkedIn activó challenge/2FA/captcha.")
            print_status("👉 Resuélvelo manualmente en el navegador.")
            print_status("👉 Cuando estés en el FEED, presiona ENTER en la consola.")
            input()

        page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        context.storage_state(path=STATE_FILE)
        print_status(f"✅ Sesión guardada en: {STATE_FILE}")
    else:
        print_status("✅ Sesión activa detectada (storage_state OK).")

def wait_feed_ready(page):
    """Espera a que el feed esté listo Y diagnostica"""
    print_status(f"🔍 URL actual: {page.url}")
    
    try:
        page.wait_for_selector("main", timeout=15000)
        print_status("✅ Elemento <main> encontrado")
    except TimeoutError:
        print_status("⚠️ No se encontró <main>")
    
    print_status("⏳ Esperando carga inicial de posts...")
    try:
        page.wait_for_selector('div[role="listitem"]', timeout=10000)
        print_status("✅ Posts detectados en el DOM")
    except TimeoutError:
        print_status("⚠️ No se detectaron posts con role='listitem'")
    
    page.wait_for_timeout(3000)
    
    print_status("\n🔬 DIAGNÓSTICO DE SELECTORES:")
    for selector in POST_SELECTORS:
        try:
            count = page.locator(selector).count()
            print_status(f"  • '{selector}': {count} elementos")
        except Exception as e:
            print_status(f"  • '{selector}': ERROR - {e}")
    
    print_status("\n🔍 Análisis de scroll...")
    scroll_info = page.evaluate("""() => {
        // Buscar el contenedor con scroll
        const main = document.querySelector('main');
        const body = document.body;
        const html = document.documentElement;
        
        return {
            window_scroll: {
                scrollY: window.scrollY,
                scrollHeight: document.documentElement.scrollHeight,
                clientHeight: document.documentElement.clientHeight
            },
            main_scroll: main ? {
                scrollTop: main.scrollTop,
                scrollHeight: main.scrollHeight,
                clientHeight: main.clientHeight,
                hasOverflow: main.scrollHeight > main.clientHeight
            } : null,
            body_scroll: {
                scrollTop: body.scrollTop,
                scrollHeight: body.scrollHeight,
                clientHeight: body.clientHeight
            }
        };
    }""")
    
    print_status(f"  • Window scroll: Y={scroll_info['window_scroll']['scrollY']}, Height={scroll_info['window_scroll']['scrollHeight']}")
    if scroll_info['main_scroll']:
        print_status(f"  • Main scroll: Top={scroll_info['main_scroll']['scrollTop']}, Height={scroll_info['main_scroll']['scrollHeight']}, HasOverflow={scroll_info['main_scroll']['hasOverflow']}")
    
    print_status("\n" + "="*60 + "\n")

def count_posts(page) -> int:
    """Cuenta posts - USA EL SELECTOR MÁS CONFIABLE"""
    return page.evaluate(
        """() => {
            const posts = document.querySelectorAll('div[role="listitem"]');
            return posts.length;
        }"""
    )

def reached_end_of_feed(page) -> bool:
    """Detecta si LinkedIn muestra mensaje de fin de feed"""
    try:
        return page.evaluate("""() => {
            const text = document.body.innerText.toLowerCase();
            return text.includes('you\'re all caught up') || 
                   text.includes('no more posts') ||
                   text.includes('reached the end') ||
                   text.includes('no hay más publicaciones') ||
                   text.includes('estás al día') ||
                   text.includes('ya estás al día');
        }""")
    except:
        return False

def scroll_feed_down(page):
    """
    Hace scroll en el feed de LinkedIn.
    Detecta automáticamente si usa scroll de window o de un contenedor.
    """
    result = page.evaluate("""() => {
        // Intentar detectar el contenedor con scroll
        const main = document.querySelector('main');
        
        // Verificar si main tiene overflow
        if (main && main.scrollHeight > main.clientHeight) {
            // Scroll en el contenedor main
            const before = main.scrollTop;
            const maxScroll = main.scrollHeight - main.clientHeight;
            
            // Scroll suave hasta el final
            const distance = maxScroll - before;
            const steps = 8;
            const stepSize = distance / steps;
            
            for (let i = 0; i < steps; i++) {
                main.scrollTop = before + (stepSize * (i + 1));
            }
            main.scrollTop = maxScroll;
            
            return {
                container: 'main',
                before: before,
                after: main.scrollTop,
                scrollHeight: main.scrollHeight
            };
        } else {
            // Scroll en window (fallback)
            const before = window.scrollY;
            const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
            
            const distance = maxScroll - before;
            const steps = 8;
            const stepSize = distance / steps;
            
            for (let i = 0; i < steps; i++) {
                window.scrollTo(0, before + (stepSize * (i + 1)));
            }
            window.scrollTo(0, maxScroll);
            
            return {
                container: 'window',
                before: before,
                after: window.scrollY,
                scrollHeight: document.documentElement.scrollHeight
            };
        }
    }""")
    
    print_status(f"   📍 Scroll en '{result['container']}': {int(result['before'])}px → {int(result['after'])}px (altura: {int(result['scrollHeight'])}px)")
    
    # Pequeñas pausas entre pasos para simular comportamiento humano
    page.wait_for_timeout(random.randint(300, 600))
    
    return result

import json
from datetime import datetime

# ... imports ...

EXTRACTED_FILE = "extracted_posts.json"

def save_posts(posts):
    try:
        with open(EXTRACTED_FILE, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print_status(f"⚠️ Error guardando JSON: {e}")

from datetime import timedelta
import re

def parse_relative_time(time_str):
    """Convierte texto como '30 min', '2 h', '1 d' a fecha aproximada"""
    try:
        now = datetime.now()
        clean_str = time_str.lower().replace("•", "").strip()
        
        # Patrones comunes
        if 'min' in clean_str or 'm' in clean_str.split() or clean_str.endswith('m'): # cuidado con meses
            # Buscar numero
            nums = re.findall(r'\d+', clean_str)
            if nums:
                minutes = int(nums[0])
                return (now - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")
        
        if 'h' in clean_str:
            nums = re.findall(r'\d+', clean_str)
            if nums:
                hours = int(nums[0])
                return (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
                
        if 'd' in clean_str or 'día' in clean_str or 'dia' in clean_str:
            nums = re.findall(r'\d+', clean_str)
            if nums:
                days = int(nums[0])
                return (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
        
        if 'sem' in clean_str or 'w' in clean_str:
            nums = re.findall(r'\d+', clean_str)
            if nums:
                weeks = int(nums[0])
                return (now - timedelta(weeks=weeks)).strftime("%Y-%m-%d %H:%M")

        if 'mes' in clean_str or 'mo' in clean_str:
            nums = re.findall(r'\d+', clean_str)
            if nums:
                months = int(nums[0])
                return (now - timedelta(days=months*30)).strftime("%Y-%m-%d %H:%M")
                
        if 'año' in clean_str or 'yr' in clean_str or 'y' in clean_str:
            nums = re.findall(r'\d+', clean_str)
            if nums:
                years = int(nums[0])
                return (now - timedelta(days=years*365)).strftime("%Y-%m-%d %H:%M")

        return time_str # Retornar original si no se pudo parsear
    except:
        return time_str

def extract_post_data(post_locator):
    """Extrae datos de un post individual"""
    try:
        # Texto del post
        text = ""
        text_elem = post_locator.locator('span[data-testid="expandable-text-box"]').first
        if text_elem.count() > 0:
            text = text_elem.inner_text().strip()
        
        # Autor y URL
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

        # Tiempo
        time_text = ""
        time_abs = ""
        
        # Estrategia mejorada para tiempo: Buscar texto que contenga "•"
        # El usuario indica que está en un <p> con "30 min •"
        
        # Buscamos elementos que contengan el punto bullet
        # Usamos locator con filtro de texto para mayor precisión
        # El texto suele ser algo como "30 min • " (con espacio)
        
        time_elem = post_locator.locator("p, span, div").filter(has_text=re.compile(r"^\d+\s*[mhdsy].*•")).first
        
        if time_elem.count() == 0:
            # Intento alternativo directo por contenido de texto que tenga bullet
            time_elem = post_locator.locator("text=/\\d+\\s*(min|h|d|sem|año|mo).*•/i").first
            
        if time_elem.count() > 0:
             raw_time = time_elem.inner_text().strip()
             # Extraemos la parte antes del bullet
             if "•" in raw_time:
                 time_part = raw_time.split("•")[0].strip()
                 time_abs = parse_relative_time(time_part)
                 time_text = time_part # Guardamos el relativo original también o el absoluto?
                 # El usuario pidió "tiempo y calculo", guardemos el calculado en time_posted
        
        # Si falló, intentar el old school link post
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
    except Exception as e:
        # print_status(f"Error extrayendo post: {e}") 
        return None

def process_posts(page, all_posts_list, seen_ids):
    """Procesa los posts visibles y guarda los nuevos"""
    posts_locators = page.locator('div[role="listitem"]').all()
    new_count = 0
    
    for p in posts_locators:
        # Usamos el texto como ID simple para evitar duplicados si no hay ID único
        # O mejor, generamos un hash del texto + autor
        data = extract_post_data(p)
        if not data or not data['text']: 
            continue
            
        # Generar ID único usando solo Autor + Texto (primeros 50 caracteres)
        # Excluimos el tiempo para evitar duplicados si cambia el formato de parsing
        unique_id = f"{data['author']}_{data['text'][:50]}"
        
        if unique_id not in seen_ids:
            seen_ids.add(unique_id)
            all_posts_list.append(data)
            new_count += 1
            
    if new_count > 0:
        print_status(f"💾 Guardados {new_count} posts nuevos (Total: {len(all_posts_list)})")
        save_posts(all_posts_list)

def scroll_until_no_more(page, max_cycles=250, stable_rounds_to_stop=6):
    """
    Scroll continuo hasta el final del feed con extracción.
    """
    wait_feed_ready(page)
    
    all_posts = []
    seen_ids = set()
    
    # Cargar previos si existen
    if Path(EXTRACTED_FILE).exists():
        try:
            with open(EXTRACTED_FILE, "r", encoding="utf-8") as f:
                all_posts = json.load(f)
                for p in all_posts:
                    if p.get('text'):
                        # Mismo ID generado en process_posts
                        uid = f"{p.get('author')}_{p.get('text')[:50]}"
                        seen_ids.add(uid)
            print_status(f"📚 Cargados {len(all_posts)} posts previos del archivo.")
        except:
            pass

    try:
        last_posts = count_posts(page)
    except TargetClosedError:
        print_status("🛑 Página cerrada antes de iniciar scroll.")
        return

    print_status(f"📌 Posts iniciales detectados: {last_posts}")
    
    if last_posts == 0:
        print_status("\n⚠️ ⚠️ ⚠️  NO SE DETECTARON POSTS ⚠️ ⚠️ ⚠️")
        print_status("Revisa el diagnóstico arriba.")
        print_status("\n👉 Presiona ENTER para continuar de todas formas o Ctrl+C para cancelar...")
        input()
        
    # Primera extracción
    process_posts(page, all_posts, seen_ids)

    stable = 0
    last_height = 0

    for cycle in range(1, max_cycles + 1):
        if page.is_closed():
            print_status("🛑 Página cerrada. Fin.")
            break

        try:
            print_status(f"\n🔄 Ciclo {cycle}:")
            
            # 🎯 SCROLL EN EL CONTENEDOR CORRECTO
            scroll_result = scroll_feed_down(page)
            current_height = scroll_result['scrollHeight']
            
            # Pausa para que LinkedIn cargue nuevos posts
            wait_time = random.randint(2500, 4000)
            print_status(f"   ⏳ Esperando {wait_time}ms para carga...")
            page.wait_for_timeout(wait_time)
            
            # EXTRAER DATOS
            process_posts(page, all_posts, seen_ids)

            # Verificar si la página creció
            if current_height > last_height and last_height > 0:
                print_status(f"   📈 Contenido creció: {last_height}px → {current_height}px")
            last_height = current_height

            # Verificar fin del feed
            if reached_end_of_feed(page):
                print_status("✅ LinkedIn indica 'fin del feed'.")
                break

            # Contar posts actuales (para lógica de parada)
            new_posts = count_posts(page)

        except TargetClosedError:
            print_status("🛑 TargetClosedError durante scroll.")
            break
        except Exception as e:
            print_status(f"⚠️ Error en ciclo {cycle}: {e}")
            break

        if new_posts > last_posts:
            diff = new_posts - last_posts
            print_status(f"📊 Posts visibles: {last_posts} → {new_posts} (+{diff})")
            last_posts = new_posts
            stable = 0
        else:
            stable += 1
            print_status(f"⏳ Sin nuevos posts visuales ({stable}/{stable_rounds_to_stop})")

        # Verificar challenge
        if is_on_challenge(page):
            print_status("⚠️ Challenge detectado. Resuélvelo y presiona ENTER.")
            input()
            try:
                page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
            except TargetClosedError:
                print_status("🛑 Error al volver del challenge.")
                break

        if stable >= stable_rounds_to_stop:
            print_status("✅ No aparece más contenido. Fin del scroll.")
            break

    print_status(f"\n🏁 FINALIZADO - Total posts guardados: {len(all_posts)}")

def main():
    load_env(ENV_FILE)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=30,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context_options = {
            "no_viewport": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }

        if Path(STATE_FILE).exists():
            context = browser.new_context(storage_state=STATE_FILE, **context_options)
        else:
            context = browser.new_context(**context_options)

        page = context.new_page()

        page.on("close", lambda: print_status("⚠️ EVENTO: page.close()"))
        page.on("crash", lambda: print_status("💥 EVENTO: page.crash()"))

        try:
            ensure_login(page, context)

            scroll_until_no_more(page, max_cycles=250, stable_rounds_to_stop=6)

            try:
                context.storage_state(path=STATE_FILE)
                print_status(f"💾 Estado guardado en: {STATE_FILE}")
            except TargetClosedError:
                pass

            input("\n✅ Listo. Presiona ENTER para cerrar...")

        except KeyboardInterrupt:
            print_status("\n🛑 Ctrl+C - detenido.")

        except Exception as e:
            print_status(f"\n❌ Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        finally:
            try:
                if not page.is_closed():
                    context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()