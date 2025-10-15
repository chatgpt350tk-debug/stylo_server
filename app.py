import os, csv, time
from flask import Flask, request, Response, jsonify
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

CATALOG_PATH = "data/dress_catalog.csv"
ORDERS_PATH  = "data/orders.csv"
SHIPPING_INSIDE_DHAKA  = 70
SHIPPING_OUTSIDE_DHAKA = 150


# ---------------- Helper Functions ----------------
def ensure_data():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f);w.writerow(["code","name","price_bdt","sizes","color","stock","image_url","video_url"])
    if not os.path.exists(ORDERS_PATH):
        with open(ORDERS_PATH,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f);w.writerow(["order_id","datetime","customer_name","phone","address","code","size","qty","price_bdt","subtotal_bdt","delivery_fee_bdt","total_with_delivery_bdt","payment_method","status"])

def find_product(code):
    ensure_data()
    with open(CATALOG_PATH,newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["code"].strip().upper()==code.strip().upper(): return r
    return None

def delivery_fee(addr:str)->int:
    a=(addr or "").lower()
    return SHIPPING_INSIDE_DHAKA if ("ঢাকা" in a or "dhaka" in a) else SHIPPING_OUTSIDE_DHAKA


# ---------------- WhatsApp Webhook ----------------
@app.route("/twilio/whatsapp", methods=["POST"])
def whatsapp_webhook():
    ensure_data()
    body=(request.form.get("Body") or "").strip()
    resp = MessagingResponse()
    q=body.lower()

    # ট্র্যাকিং
    if any(k in q for k in ["কতদূর","কোথায়","কোথায়","where is","status","track","tracking"]):
        resp.message("আপনার Order ID লিখুন (যেমন ORD-12345) — আমি স্ট্যাটাস বলে দেব।")
        return Response(str(resp), mimetype="application/xml")

    # প্রোডাক্ট কোড (যেমন DR-1050)
    code=None
    for t in body.upper().replace(","," ").split():
        if "-" in t or t.startswith("DR"): code=t;break
    if code:
        it=find_product(code)
        if it:
            msg=[f"{it['name']} ({it['code']})",
                 f"দাম: {it['price_bdt']}৳ | স্টক: {it['stock']}",
                 f"সাইজ: {it['sizes']} | রং: {it['color']}",
                 f"ডেলিভারি: ঢাকার মধ্যে {SHIPPING_INSIDE_DHAKA}৳, বাইরে {SHIPPING_OUTSIDE_DHAKA}৳"]
            if it.get("image_url"): msg.append(f"ছবি: {it['image_url']}")
            if it.get("video_url"): msg.append(f"ভিডিও: {it['video_url']}")
            resp.message("\n".join(msg))
        else:
            resp.message("এই কোডটি পাওয়া যায়নি। সঠিক কোড দিন বা ছবি/ভিডিও লিংক দিন।")
        return Response(str(resp), mimetype="application/xml")

    # অর্ডার শুরু
    if any(x in q for x in ["অর্ডার","order","কিনবো","নেবো","নিবো"]):
        resp.message("অর্ডার করতে নাম/মোবাইল/ঠিকানা/কোড/সাইজ/Qty লিখে দিন। উদাহরণ:\nনাম: রফিক\nফোন: 01...\nঠিকানা: মিরপুর, ঢাকা\nকোড: DR-1050\nসাইজ: L\nQty: 1")
        return Response(str(resp), mimetype="application/xml")

    # ডিফল্ট
    resp.message("হ্যালো 👋 STYLO থেকে বলছি! প্রোডাক্ট কোড পাঠান—দাম/স্টক জানাচ্ছি। অর্ডার করতে নাম/ঠিকানা লিখে দিন।")
    return Response(str(resp), mimetype="application/xml")


# ---------------- Admin: Create Order ----------------
@app.route("/admin/create_order", methods=["POST"])
def create_order():
    ensure_data()
    f={k:(request.form.get(k) or "") for k in ["customer_name","phone","address","code","size","qty","price_bdt","payment_method"]}
    qty=int(f.get("qty") or 1)
    price=int(f.get("price_bdt") or 0)
    subtotal=price*qty
    fee=delivery_fee(f.get("address",""))
    total=subtotal+fee
    oid=f"ORD-{int(time.time())}"
    with open(ORDERS_PATH,"a",newline="",encoding="utf-8") as out:
        w=csv.writer(out)
        w.writerow([oid,time.strftime("%Y-%m-%d %H:%M"),f["customer_name"],f["phone"],f["address"],f["code"],f["size"],qty,price,subtotal,fee,total,f.get("payment_method","COD"),"NEW"])
    return jsonify({"ok":True,"order_id":oid,"total":total})


# ---------------- Admin: Add Product (Zapier Path–2) ----------------
@app.route("/admin/add_product", methods=["POST"])
def add_product():
    ensure_data()
    f = {k:(request.form.get(k) or "") for k in
         ["code","name","price_bdt","sizes","color","stock","image_url","video_url"]}
    # ডুপ্লিকেট চেক
    with open(CATALOG_PATH, newline="", encoding="utf-8") as f_in:
        for r in csv.DictReader(f_in):
            if r["code"].strip().upper()==f["code"].strip().upper():
                return jsonify({"ok":False,"error":"Code already exists"}), 400
    # নতুন প্রোডাক্ট যোগ
    newfile = os.path.exists(CATALOG_PATH) and os.path.getsize(CATALOG_PATH)>0
    with open(CATALOG_PATH,"a",newline="",encoding="utf-8") as f_out:
        cols=["code","name","price_bdt","sizes","color","stock","image_url","video_url"]
        w = csv.DictWriter(f_out, fieldnames=cols)
        if not newfile: w.writeheader()
        w.writerow({k:f.get(k,"") for k in cols})
    return jsonify({"ok":True,"message":"Product added successfully!"})


# ---------------- Health Check ----------------
@app.get("/health")
def health(): 
    return {"ok":True},200


if __name__=="__main__":
    ensure_data()
    app.run(host="0.0.0.0",port=5000)
