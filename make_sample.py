import csv
from pathlib import Path

ROWS = [
 ("Senior Software Engineer","Acme Cloud","Nairobi, Kenya","Mid senior","Onsite","python, aws, docker, sql"),
 ("Software Engineer","Acme Cloud","Remote","Associate","Remote","python, fastapi, postgresql"),
 ("Backend Engineer","Baobab Pay","Nairobi, Kenya","Mid senior","Hybrid","python, django, postgresql, redis"),
 ("Junior Python Developer","Baobab Pay","Mombasa, Kenya","Entry level","Onsite","python, git, sql"),
 ("Full Stack Developer","Savanna Labs","Kisumu, Kenya","Associate","Hybrid","javascript, react, node.js, sql"),
 ("Frontend Engineer","Savanna Labs","Remote","Associate","Remote","javascript, typescript, react, css"),
 ("Rust Systems Engineer","Ironwood Systems","Berlin, Germany","Mid senior","Onsite","rust, linux, c++, networking"),
 ("Platform Engineer","Ironwood Systems","Berlin, Germany","Mid senior","Hybrid","kubernetes, docker, aws, python"),
 ("DevOps Engineer","Northwind Tech","London, England","Mid senior","Hybrid","aws, terraform, docker, kubernetes"),
 ("Software Engineer Intern","Northwind Tech","London, England","Internship","Onsite","python, git, sql"),
 ("Machine Learning Engineer","Kilimanjaro AI","Remote","Mid senior","Remote","python, pytorch, sql, aws"),
 ("Data Engineer","Kilimanjaro AI","Nairobi, Kenya","Associate","Hybrid","python, spark, sql, airflow"),
 ("Security Engineer","Cobalt Secure","Austin, TX","Mid senior","Onsite","python, owasp, oauth, linux"),
 ("Application Security Engineer","Cobalt Secure","Remote","Mid senior","Remote","oauth, jwt, python, owasp"),
 ("Mobile Developer","Pixel Harbor","San Francisco, CA","Associate","Onsite","kotlin, swift, git"),
 ("Android Engineer","Pixel Harbor","San Francisco, CA","Mid senior","Hybrid","kotlin, java, git"),
 ("QA Engineer","Testbridge","Remote","Associate","Remote","python, selenium, pytest, sql"),
 ("Senior Backend Engineer","Testbridge","Toronto, Canada","Mid senior","Hybrid","go, postgresql, docker, aws"),
 ("Software Engineer","Lakeside Health","Nairobi, Kenya","Entry level","Onsite","java, spring, sql"),
 ("Cloud Engineer","Lakeside Health","Remote","Mid senior","Remote","azure, terraform, python"),
 ("Python Developer","Delta Analytics","Pune, India","Associate","Onsite","python, pandas, sql, flask"),
 ("Senior Software Engineer","Delta Analytics","Pune, India","Mid senior","Hybrid","python, aws, kafka, sql"),
 ("Rust Engineer","Ferrous Labs","Remote","Mid senior","Remote","rust, tokio, linux"),
 ("Junior Software Engineer","Ferrous Labs","Amsterdam, Netherlands","Entry level","Onsite","rust, python, git"),
]

out = Path(__file__).parent / "data" / "sample_postings.csv"
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["job_title","company","job_location","job_link","first_seen","search_city",
                "search_country","job_level","job_type","job_summary","job_skills"])
    for i,(t,c,l,lv,jt,sk) in enumerate(ROWS, 1):
        w.writerow([t,c,l,f"https://example.com/jobs/{i}","2024-01-15",l.split(",")[0],
                    "Sample",lv,jt,f"Synthetic sample posting for a {t} at {c}.",sk])
print("wrote", out, len(ROWS), "rows")