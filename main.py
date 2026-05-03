import os
import sys
import base64
import time
import requests
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from dotenv import load_dotenv
from colorama import init, Fore, Style

load_dotenv()
init(autoreset=True)

# ─────────────────────────────────────────────
# Step 1: QR Code Decoding
# ─────────────────────────────────────────────

def decode_qr(image_path: str) -> list[str]:
    """Decode all QR codes from an image and return a list of URLs."""
    if not os.path.exists(image_path):
        print(Fore.RED + f"[ERROR] File not found: {image_path}")
        sys.exit(1)

    # Use numpy to handle paths with non-ASCII/Unicode characters (e.g. Turkish, Chinese)
    try:
        with open(image_path, "rb") as f:
            img_array = np.frombuffer(f.read(), dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except Exception as e:
        print(Fore.RED + f"[ERROR] Could not read image file: {e}")
        sys.exit(1)

    if img is None:
        print(Fore.RED + f"[ERROR] Could not decode image: {image_path}")
        sys.exit(1)

    decoded_objects = decode(img)
    if not decoded_objects:
        print(Fore.YELLOW + "[WARNING] No QR code detected in the image.")
        sys.exit(0)

    urls = [obj.data.decode("utf-8") for obj in decoded_objects]
    return urls


# ─────────────────────────────────────────────
# Step 2: URL Unshortener
# ─────────────────────────────────────────────

SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly",
    "buff.ly", "short.link", "rb.gy", "is.gd", "v.gd",
}

def is_shortened(url: str) -> bool:
    """Check if a URL belongs to a known URL shortener."""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return domain in SHORTENER_DOMAINS
    except Exception:
        return False

def unshorten_url(url: str) -> str:
    """Follow redirect chain via HEAD request and return the final URL."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        # Some servers don't respond to HEAD, fall back to GET
        if response.status_code in (405, 403):
            response = requests.get(url, allow_redirects=True, timeout=10, stream=True)
            response.close()

        if len(response.history) > 0:
            print(Fore.CYAN + f"  Redirect chain ({len(response.history)} hop(s)):")
            for i, r in enumerate(response.history, 1):
                print(Fore.CYAN + f"    {i}. [{r.status_code}] {r.url}")

        return response.url
    except requests.RequestException as e:
        print(Fore.YELLOW + f"[WARNING] Could not follow redirects: {e}")
        return url


# ─────────────────────────────────────────────
# Step 3: VirusTotal v3 Integration
# ─────────────────────────────────────────────

VT_API_BASE = "https://www.virustotal.com/api/v3"

def analyze_url_virustotal(url: str) -> dict:
    """Submit URL to VirusTotal and return parsed threat summary."""
    api_key = os.getenv("VIRUSTOTAL_API_KEY")
    if not api_key or api_key == "your_virustotal_api_key_here":
        print(Fore.RED + "[ERROR] VIRUSTOTAL_API_KEY is not set in your .env file.")
        sys.exit(1)

    headers = {"x-apikey": api_key}

    # Submit URL for analysis
    url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    submit_resp = requests.post(
        f"{VT_API_BASE}/urls",
        headers=headers,
        data={"url": url},
        timeout=15,
    )

    if submit_resp.status_code not in (200, 201):
        print(Fore.RED + f"[ERROR] VirusTotal submission failed: {submit_resp.status_code}")
        sys.exit(1)

    # Poll for the analysis result
    analysis_id = submit_resp.json().get("data", {}).get("id")
    if not analysis_id:
        # Fall back to direct URL lookup
        analysis_id = url_id

    for attempt in range(6):
        report_resp = requests.get(
            f"{VT_API_BASE}/urls/{url_id}",
            headers=headers,
            timeout=15,
        )
        if report_resp.status_code == 200:
            break
        time.sleep(3)
    else:
        print(Fore.RED + "[ERROR] Could not retrieve VirusTotal report after retries.")
        sys.exit(1)

    data = report_resp.json().get("data", {})
    stats = data.get("attributes", {}).get("last_analysis_stats", {})
    categories = data.get("attributes", {}).get("categories", {})

    malicious = stats.get("malicious", 0)
    harmless = stats.get("harmless", 0)
    suspicious = stats.get("suspicious", 0)
    undetected = stats.get("undetected", 0)

    # Collect unique category labels from all engines
    unique_categories = list(set(categories.values())) if categories else []

    return {
        "malicious": malicious,
        "harmless": harmless,
        "suspicious": suspicious,
        "undetected": undetected,
        "categories": unique_categories,
    }


# ─────────────────────────────────────────────
# Step 4: CLI Interface & Logic Flow
# ─────────────────────────────────────────────

def threat_color(malicious: int) -> str:
    if malicious == 0:
        return Fore.GREEN
    elif malicious <= 3:
        return Fore.YELLOW
    else:
        return Fore.RED

def print_report(original_url: str, final_url: str, report: dict) -> None:
    color = threat_color(report["malicious"])
    redirected = original_url != final_url

    print("\n" + "=" * 60)
    print(Style.BRIGHT + "  QR CODE SECURITY ANALYSIS REPORT")
    print("=" * 60)
    print(f"  {'Original URL':<18}: {original_url}")
    if redirected:
        print(f"  {'Final URL':<18}: {Fore.CYAN}{final_url}{Style.RESET_ALL}")
    print(f"  {'Redirected':<18}: {'Yes' if redirected else 'No'}")
    print("-" * 60)
    print(f"  {'Malicious':<18}: {color}{report['malicious']}{Style.RESET_ALL}")
    print(f"  {'Suspicious':<18}: {Fore.YELLOW}{report['suspicious']}{Style.RESET_ALL}")
    print(f"  {'Harmless':<18}: {Fore.GREEN}{report['harmless']}{Style.RESET_ALL}")
    print(f"  {'Undetected':<18}: {report['undetected']}")

    if report["categories"]:
        print(f"  {'Categories':<18}: {', '.join(report['categories'])}")

    verdict = (
        color + "  SAFE" if report["malicious"] == 0
        else color + "  SUSPICIOUS" if report["malicious"] <= 3
        else color + "  DANGEROUS"
    )
    print("-" * 60)
    print(f"  Verdict: {Style.BRIGHT}{verdict}{Style.RESET_ALL}")
    print("=" * 60 + "\n")


def main():
    print(Style.BRIGHT + Fore.CYAN + "\n  QR Code Malicious URL Analyzer")
    print(Fore.CYAN + "  ================================\n")

    image_path = input("  Enter image path: ").strip()

    # Step 1 – Decode QR
    print(Fore.CYAN + "\n  [1/3] Reading QR code(s)...")
    urls = decode_qr(image_path)
    print(Fore.GREEN + f"  Found {len(urls)} QR code(s).")

    for idx, url in enumerate(urls, start=1):
        if len(urls) > 1:
            print(Style.BRIGHT + f"\n  ── QR Code #{idx} ──")

        print(Fore.CYAN + f"  Original URL : {url}")

        # Step 2 – Follow all redirects unconditionally
        print(Fore.CYAN + "\n  [2/3] Following redirects...")
        final_url = unshorten_url(url)
        if final_url != url:
            print(Fore.GREEN + f"  Redirect detected!")
            print(Fore.GREEN + f"  Final URL    : {final_url}")
        else:
            print(Fore.GREEN + "  No redirect detected, URL is direct.")

        # Step 3 – VirusTotal
        print(Fore.CYAN + "\n  [3/3] Running security analysis via VirusTotal...")
        report = analyze_url_virustotal(final_url)

        # Step 4 – Display report
        print_report(url, final_url, report)


if __name__ == "__main__":
    main()
