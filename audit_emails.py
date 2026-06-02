import json
import re

def audit_emails():
    with open('extracted_posts.json', 'r', encoding='utf-8') as f:
        posts = json.load(f)
        
    email_pattern = r'[a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}'
    
    found_count = 0
    for i, post in enumerate(posts):
        text = post.get('text', '')
        emails = re.findall(email_pattern, text, re.IGNORECASE)
        if emails:
            found_count += len(emails)
            print(f"Post {i}: Found {emails}")
            if found_count > 10: break
            
    print(f"Audit complete. Sample found: {found_count} contacts.")

if __name__ == "__main__": audit_emails()
