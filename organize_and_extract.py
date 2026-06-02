import os
import csv
import shutil

base_dir = r"d:\PROGRAMACION\Linkedin-Email-Extractor"

# 1. Extract emails
connections_file = os.path.join(base_dir, "Connections.csv")
output_emails_file = os.path.join(base_dir, "Contactos_con_Correos.csv")

emails_found = []

if os.path.exists(connections_file):
    with open(connections_file, 'r', encoding='utf-8') as f:
        # Skip first 3 lines
        for _ in range(3):
            next(f)
        
        reader = csv.reader(f)
        try:
            header = next(reader)
            if "Email Address" in header:
                email_idx = header.index("Email Address")
                for row in reader:
                    if len(row) > email_idx:
                        email = row[email_idx].strip()
                        if email:
                            emails_found.append({
                                'First Name': row[0],
                                'Last Name': row[1],
                                'Email': email,
                                'Company': row[4] if len(row) > 4 else '',
                                'Position': row[5] if len(row) > 5 else ''
                            })
        except Exception as e:
            print(f"Error reading CSV: {e}")

if emails_found:
    with open(output_emails_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['First Name', 'Last Name', 'Email', 'Company', 'Position'])
        writer.writeheader()
        writer.writerows(emails_found)
    print(f"Extracted {len(emails_found)} contacts with emails to {output_emails_file}")
else:
    print("No emails found in Connections.csv")

# 2. Organize files
categories = {
    "Red_y_Contactos": [
        "Connections.csv", "Invitations.csv", "PhoneNumbers.csv", 
        "Whatsapp Phone Numbers.csv", "Events.csv", "Company Follows.csv"
    ],
    "Perfil": [
        "Profile.csv", "Profile Summary.csv", "Positions.csv", 
        "Education.csv", "Skills.csv", "Languages.csv", "Certifications.csv", 
        "Email Addresses.csv", "Private_identity_asset.csv", "Registration.csv",
        "Endorsement_Given_Info.csv", "Endorsement_Received_Info.csv"
    ],
    "Mensajes": [
        "messages.csv", "guide_messages.csv", "learning_coach_messages.csv", 
        "learning_role_play_messages.csv"
    ],
    "Empleos": [
        "SavedJobAlerts.csv", "Job Applicant Saved Screening Question Responses.csv", 
        "Job Applicant Saved Screening Question Responses_1.csv", "Jobs"
    ],
    "Aprendizaje": [
        "Learning.csv"
    ],
    "Multimedia_y_Otros": [
        "Rich_Media.csv", "Figura 9.svg", "Figura 10.svg", 
        "index.html", "technical_illustration.html", "Verifications"
    ],
    "Anuncios_y_Pagos": [
        "Ad_Targeting.csv", "Receipts_v2.csv"
    ]
}

for folder, files in categories.items():
    folder_path = os.path.join(base_dir, folder)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    
    for item in files:
        item_path = os.path.join(base_dir, item)
        if os.path.exists(item_path):
            try:
                shutil.move(item_path, os.path.join(folder_path, item))
                print(f"Moved {item} to {folder}/")
            except Exception as e:
                print(f"Failed to move {item}: {e}")

print("Organization complete.")
