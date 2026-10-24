"""All user-facing text lives here, in Swahili. To add English later, add a second
dictionary and pick one by language setting."""

SW = {
    "app_name": "Kiosk Manager",
    "nav_stock": "Stoo",
    "nav_sell": "Uza",
    "nav_add": "Ongeza",
    "nav_report": "Ripoti",

    "stock_title": "Bidhaa zilizopo",
    "search_placeholder": "Tafuta bidhaa...",
    "search_button": "Tafuta",
    "clear_search": "Futa utafutaji",
    "no_matches": "Hakuna bidhaa iliyopatikana.",
    "no_products": "Hakuna bidhaa bado. Ongeza ya kwanza.",
    "col_product": "Bidhaa",
    "col_price": "Bei",
    "col_qty": "Idadi",
    "col_total": "Jumla",
    "col_time": "Wakati",
    "low": "Inaisha",
    "out": "Imeisha",

    "sell_title": "Uza bidhaa",
    "choose_product": "Chagua bidhaa",
    "quantity": "Idadi",
    "sell_button": "Uza",
    "left": "zimebaki",
    "nothing_to_sell": "Hakuna bidhaa za kuuza. Ongeza stoo kwanza.",

    "add_title": "Ongeza au jaza stoo",
    "product_name": "Jina la bidhaa",
    "price_label": "Bei (KES)",
    "price_hint": "Weka bei ikiwa bidhaa ni mpya tu.",
    "add_button": "Hifadhi",

    "report_title": "Ripoti ya mauzo",
    "today": "Leo",
    "all_time": "Yote",
    "revenue": "Mapato",
    "products_sold": "Bidhaa tofauti",
    "best_seller": "Inayouzwa zaidi",
    "units": "vipande",
    "no_sales": "Hakuna mauzo bado.",
    "sales_list": "Mauzo",

    "sold_ok": "Umeuza {quantity} {product} kwa KES {total}.",
    "restocked_ok": "{product} imejazwa. Idadi mpya: {quantity}.",
    "added_ok": "{product} imeongezwa.",

    "err_invalid_name": "Weka jina sahihi la bidhaa.",
    "err_invalid_number_quantity": "Idadi lazima iwe namba nzima kubwa kuliko 0.",
    "err_invalid_number_price": "Bei lazima iwe namba nzima kubwa kuliko 0.",
    "err_unknown_product": "{name} haipo kwenye stoo.",
    "err_not_enough": "Stoo haitoshi. Zimebaki {available} tu.",
    "err_price_required": "{name} ni bidhaa mpya, weka bei.",
    "err_empty_search": "Andika kitu cha kutafuta.",

    "login_title": "Ingia",
    "email": "Barua pepe",
    "password": "Nenosiri",
    "password_hint": "Angalau herufi 8.",
    "login_button": "Ingia",
    "no_account": "Huna akaunti?",
    "register_link": "Jisajili",
    "register_title": "Fungua akaunti",
    "kiosk_name_label": "Jina la duka",
    "register_button": "Jisajili",
    "have_account": "Tayari una akaunti?",
    "demo_button": "Jaribu demo",
    "demo_hint": "Jaribu bila kujisajili. Data ya demo hufutwa baada ya saa 24.",
    "logout": "Toka",
    "welcome_user": "Karibu, {kiosk}!",
    "logged_out": "Umetoka.",
    "or": "au",

    "err_invalid_email": "Weka barua pepe sahihi.",
    "err_weak_password": "Nenosiri liwe na herufi angalau 8.",
    "err_email_taken": "Barua pepe hii tayari imesajiliwa.",
    "err_bad_login": "Barua pepe au nenosiri si sahihi.",
    "err_invalid_kiosk_name": "Weka jina la duka.",
    "err_too_many_attempts": "Umejaribu mara nyingi. Subiri dakika 15.",
    "err_csrf": "Ombi halikuthibitishwa. Jaribu tena.",
}


def error_text(err):
    """Translate a KioskError into Swahili."""
    key = f"err_{err.code}"
    if err.code == "invalid_number":
        key += "_" + err.params["field"]
    return SW[key].format(**err.params)
