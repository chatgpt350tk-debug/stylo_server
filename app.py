# app.py
import os, csv, re
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# ----------------------------
# Basic health route (Render test)
# ----------------------------
@app.route("/health")
def health():
    return {"ok": True}

# ----------------------------
# Data paths
# ----------------------------
DATA_DIR = "data"
FAQ_PATH = os.path.join(DATA_DIR, "faq.csv")
CONTACTS_PATH = os.path.join(DATA_DIR, "contacts_prefs.csv")
ORDERS_PATH = os.path.join(DATA_DIR, "orders.csv")  # ভবিষ্যৎ use (লগ রাখার জন্য)

def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)

def ensure_faq():
    ensure_dirs()
    if not os.path.exists(FAQ_PATH):
        with open(FAQ_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["question","keywords","answer"])

def ensure_contacts():
    ensure_dirs()
    if not os.path.exists(CONTACTS_PATH):
        with open(CONTACTS_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["phone","salutation"])

def ensure_orders():
    ensure_dirs()
    if not os.path.exists(ORDERS_PATH):
        with open(ORDERS_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(
                ["order_id","name","phone","address","code","size","qty","city","status"]
            )

# ----------------------------
# Salutation (Sir/Ma'am) memory
# ----------------------------
def get_saved_salutation(phone:str):
    ensure_contacts()
    with open(CONTACTS_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("phone") or "").strip() == (phone or "").strip():
                return (r.get("salutation") or "").strip()
    return None

def save_salutation(phone:str, salutation:str):
    ensure_contacts()
    rows, seen = [], False
    with open(CONTACTS_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    for r in rows:
        if r["phone"].strip() == phone.strip():
            r["salutation"] = salutation
            seen = True
            break
    if not seen:
        rows.append({"phone":phone, "salutation":salutation})
    with open(CONTACTS_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["phone","salutation"])
        w.writeheader()
        for r in rows: w.writerow(r)

def infer_salutation_from_text(text:str):
    q = (text or "").lower()
    if any(k in q for k in ["apu","apa","আপু","আপা","ম্যাম","ma'am","madam","ম্যাডাম"]):
        return "ম্যাম"
    if any(k in q for k in ["vai","bhai","ভাই","স্যার","sir","দাদা"]):
        return "স্যার"
    return None

def salutation_for_user(phone:str, text:str):
    saved = get_saved_salutation(phone)
    if saved: return saved, False
    inferred = infer_salutation_from_text(text)
    if inferred:
        save_salutation(phone, inferred)
        return inferred, False
    return None, True  # need to ask once

# ----------------------------
# FAQ + Small talk
# ----------------------------
def answer_from_faq(user_text: str):
    ensure_faq()
    if not os.path.exists(FAQ_PATH): return None
    txt = (user_text or "").strip().lower()
    with open(FAQ_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            keys = [k.strip() for k in (r.get("keywords","") or "").lower().split(",") if k.strip()]
            if any(k in txt for k in keys):
                return (r.get("answer") or "").strip()
    return None

def small_talk(user_text: str):
    q = (user_text or "").strip().lower()
    hi = ["hi","hello","hey","সালাম","হ্যালো","হাই","assalamu"]
    bad = ["bokachoda","চোদা","ফাক","bc","mc","মাদার","গালি"]
    if any(w in q for w in hi):
        return "হ্যালো 👋 STYLO থেকে বলছি! কীভাবে সাহায্য করতে পারি?"
    if any(w in q for w in bad):
        return "আপনার কষ্টটা বুঝি—শান্তভাবে বললে দ্রুত ও ভালোভাবে সাহায্য করতে পারব। 🙏"
    if "ধন্যবাদ" in q or "thanks" in q or "thank you" in q:
        return "ধন্যবাদ! আরও কিছু লাগলে জানাবেন। 😊"
    return None

# ----------------------------
# Helpers: charge + simple order parse
# ----------------------------
def delivery_charge_for_city(city_text:str):
    # ঢাকার মধ্যে ৭০, ঢাকার বাইরে ১৫০
    t = (city_text or "").lower()
    dhaka_keys = ["dhaka","ঢাকা","mirpur","uttara","banani","dhanmondi","মিরপুর","উত্তরা","ধানমন্ডি","বনানী","গুলশান"]
    if any(k in t for k in dhaka_keys):
        return 70
    return 150

def parse_order_freeform(text: str):
    """
    ইউজার যদি একসাথে সব পাঠায়—তা হলে মিনিমাল পার্স।
    প্রত্যাশিত কিওয়ার্ড: নাম, মোবাইল/ফোন, ঠিকানা, কোড, সাইজ, Qty/পরিমাণ/qty
    """
    q = (text or "")
    def find(pattern): 
        m = re.search(pattern, q, flags=re.IGNORECASE)
        return m.group(1).strip() if m else ""
    name = find(r"নাম[:：]\s*([^\n,]+)")
    phone = find(r"(?:মোবাইল|ফোন)[:：]\s*([0-9+ \-]+)")
    address = find(r"(?:ঠিকানা|address)[:：]\s*([^\n]+)")
    code = find(r"(?:কোড|code)[:：]\s*([A-Za-z0-9\-]+)")
    size = find(r"(?:সাইজ|size)[:：]\s*([A-Za-z0-9/]+)")
    qty = find(r"(?:qty|পরিমাণ|পিস)[:：]?\s*([0-9]+)")
    city_guess = "ঢাকা" if "ঢাকা" in address or "dhaka" in address.lower() else ""
    return {
        "name": name, "phone": phone, "address": address,
        "code": code, "size": size, "qty": qty or "1", "city": city_guess
    }

def format_order_summary(o: dict, price=None):
    lines = [
        f"নাম: {o.get('name','')}",
        f"মোবাইল: {o.get('phone','')}",
        f"ঠিকানা: {o.get('address','')}",
        f"কোড: {o.get('code','')} | সাইজ: {o.get('size','')} | Qty: {o.get('qty','1')}",
    ]
    if price:
        qty = int(o.get("qty","1") or "1")
        sub = price * qty
        chg = delivery_charge_for_city(o.get("address",""))
        total = sub + chg
        lines += [f"পণ্যের দাম: {sub}৳", f"ডেলিভারি: {chg}৳", f"মোট বিল: {total}৳ (COD)"]
    return "\n".join(lines)

# ----------------------------
# WhatsApp webhook
# ----------------------------
@app.route("/twilio/whatsapp", methods=["POST"])
def whatsapp_webhook():
    body = (request.values.get("Body") or "").strip()
    from_num = (request.values.get("From") or "").strip()
    resp = MessagingResponse()

    # salutation (sir/ma'am) memory
    sal, need_to_ask = salutation_for_user(from_num, body)
    def greet_prefix(): return f"{sal} " if sal else ""

    # if not known, ask once
    if need_to_ask and not any(k in body.lower() for k in ["স্যার","ম্যাম","sir","madam","আপু","ভাই"]):
        resp.message("আপনাকে কীভাবে সম্বোধন করবো? ‘স্যার’ না ‘ম্যাম’ — যেটা লিখে দিন 🙂")
        return Response(str(resp), mimetype="application/xml")

    # user chooses salutation now
    if any(k in body.lower() for k in ["স্যার","ম্যাম","sir","madam"]):
        choice = "ম্যাম" if ("ম্যাম" in body.lower() or "madam" in body.lower()) else "স্যার"
        save_salutation(from_num, choice)
        resp.message(f"ধন্যবাদ! সামনে থেকে আপনাকে **{choice}** বলে সম্বোধন করব। কীভাবে সাহায্য করতে পারি?")
        return Response(str(resp), mimetype="application/xml")

    # showroom/address quick intent
    showroom_keys = ["শোরুম","দোকান","শপ","ঠিকানা","এড্রেস","address","location","লোকেশন"]
    if any(k in body.lower() for k in showroom_keys):
        resp.message(greet_prefix() + "আমাদের ফিজিক্যাল শোরুম নেই—**STYLO অনলাইন-ভিত্তিক**। ঢাকায় ডেলিভারি ৭০৳, ঢাকার বাইরে ১৫০৳। পিকআপ লোকেশন দরকার হলে জানান, ম্যানেজ করার চেষ্টা করব।")
        return Response(str(resp), mimetype="application/xml")

    # ORDER FLOW (সাধারণ: ইউজার 'অর্ডার' বললে ফরম্যাট শেয়ার)
    if any(k in body.lower() for k in ["অর্ডার", "order", "কিনতে চাই", "অর্ডার করতে চাই"]) and "নাম:" not in body:
        msg = (
            greet_prefix() + "অর্ডার করতে এই ফরম্যাটে পাঠান:\n"
            "নাম: ...\nমোবাইল: ...\nঠিকানা: ...\nকোড: ...\nসাইজ: ...\nQty: 1\n"
            "উদা: নাম: রফিক, মোবাইল: 017..., ঠিকানা: মিরপুর, কোড: DR-1050, সাইজ: L, Qty: 1"
        )
        resp.message(msg)
        return Response(str(resp), mimetype="application/xml")

    # If user already sent formatted order
    if "নাম:" in body and "মোবাইল" in body and ("কোড:" in body or "code:" in body.lower()):
        ensure_orders()
        o = parse_order_freeform(body)
        # demo: dummy price lookup (তোমার ক্যাটালগ লাগালে এখানে পড়বে)
        dummy_price = 1050 if o.get("code") else None
        summary = format_order_summary(o, price=dummy_price)
        # (ডেটাবেজে/CSV তে সংরক্ষণ করতে চাইলে এখানে লিখে দেবে)
        resp.message(greet_prefix() + "আপনার অর্ডার ডিটেইলস:\n" + summary + "\n\n✔️ কনফার্ম করব, ধন্যবাদ!")
        return Response(str(resp), mimetype="application/xml")

    # FAQ
    faq_ans = answer_from_faq(body)
    if faq_ans:
        resp.message(greet_prefix() + faq_ans)
        return Response(str(resp), mimetype="application/xml")

    # Small talk
    st = small_talk(body)
    if st:
        resp.message(greet_prefix() + st)
        return Response(str(resp), mimetype="application/xml")

    # Default fallback
    resp.message(
        greet_prefix()
        + "হ্যালো 👋 STYLO থেকে বলছি! প্রোডাক্ট কোড দিলে দাম/স্টক বলব।\n"
          "অর্ডার করতে: নাম/মোবাইল/ঠিকানা/কোড/সাইজ/Qty লিখে দিন।\n"
          "সাধারণ প্রশ্ন করতে পারেন—ডেলিভারি, চার্জ, সাইজ, রিটার্ন ইত্যাদি।"
    )
    return Response(str(resp), mimetype="application/xml")


# ----------------------------
# (Optional) Facebook Messenger webhook skeleton
# ----------------------------
# NOTE: Messenger চালু করলে এই রুট ব্যবহার করো এবং FB tokens env থেকে নেবে।
# import requests
# @app.route('/facebook', methods=['GET','POST'])
# def facebook_webhook():
#     if request.method == 'GET':
#         verify = os.getenv("FB_VERIFY_TOKEN", "stylo_fb_verify")
#         mode = request.args.get("hub.mode")
#         token = request.args.get("hub.verify_token")
#         challenge = request.args.get("hub.challenge")
#         if mode == "subscribe" and token == verify:
#             return challenge, 200
#         return "Verification failed", 403
#     data = request.get_json(force=True)
#     # এখানে data থেকে টেক্সট নিয়ে answer_from_faq/small_talk/ইত্যাদি কল করে
#     # send_facebook_message() দিয়ে উত্তর পাঠাবে।
#     return "EVENT_RECEIVED", 200


if __name__ == "__main__":
    # লোকাল টেস্টের জন্য
    app.run(host="0.0.0.0", port=10000)
