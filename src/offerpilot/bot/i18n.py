"""All user-facing bot strings, in English / romanized Hindi / romanized
Punjabi — matching the style already used for offer labels in
rules/offer_catalogue.yaml and bot/cards.py. Centralised here so Phase 5's
new commands (/why, /simulate, /preferences, /stop, /feedback, negotiation)
don't scatter ad-hoc strings across handler files.
"""
SUPPORTED_LANGUAGES = {"en", "hi", "pa"}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "greeting": {
        "en": "Hi {name}! This is OfferPilot (demo — synthetic data only).",
        "hi": "Namaste {name}! Yeh OfferPilot hai (demo — sirf synthetic data).",
        "pa": "Sat Sri Akal {name}! Eh OfferPilot hai (demo — sirf synthetic data).",
    },
    "consent_intro": {
        "en": (
            "Before we start: this is a hackathon demo. {name} is a made-up "
            "shopper profile with fake purchase history — nothing here is real. "
            "An AI agent will decide, on its own, whether to send you an offer "
            "and what it should be. Okay to continue?"
        ),
        "hi": (
            "Shuru karne se pehle: yeh ek hackathon demo hai. {name} ek fake "
            "shopper profile hai, fake purchase history ke saath — yahan kuch "
            "bhi real nahi hai. Ek AI agent khud decide karega ki aapko offer "
            "bhejna hai ya nahi, aur kya. Aage badhein?"
        ),
        "pa": (
            "Shuru karan toh pehla: eh ik hackathon demo hai. {name} ik fake "
            "shopper profile hai, fake purchase history naal — ethe kuch vi "
            "real nahi hai. Ik AI agent khud decide karega ki tuhanu offer "
            "bhejna hai ki nahi, te ki. Agge vadho?"
        ),
    },
    "consent_accept_button": {"en": "Yes, continue", "hi": "Haan, aage badhein", "pa": "Haan, agge vadho"},
    "consent_decline_button": {"en": "No thanks", "hi": "Nahi dhanyavaad", "pa": "Nahi shukriya"},
    "consent_declined": {
        "en": "No problem — nothing will be sent. Send /start anytime to change your mind.",
        "hi": "Koi baat nahi — kuch nahi bheja jayega. Mann badalne par kabhi bhi /start karein.",
        "pa": "Koi gal nahi — kujh nahi bhejia jayega. Mann badalan te kadi vi /start karo.",
    },
    "no_offer_text": {
        "en": "Nothing new for you right now — check back soon!",
        "hi": "Abhi aapke liye koi naya offer nahi hai — jald hi dobara dekhein!",
        "pa": "Hun tuhade layi koi nava offer nahi hai — jaldi dubara vekho!",
    },
    "claim_button": {"en": "✅ Claim", "hi": "✅ Claim karein", "pa": "✅ Claim karo"},
    "view_cart_button": {"en": "🛒 View cart", "hi": "🛒 Cart dekhein", "pa": "🛒 Cart vekho"},
    "not_interested_button": {"en": "🙅 Not interested", "hi": "🙅 Interested nahi", "pa": "🙅 Interested nahi"},
    "why_button": {"en": "❓ Why this offer?", "hi": "❓ Yeh offer kyun?", "pa": "❓ Eh offer kyun?"},
    "claimed_response": {
        "en": "Claimed! (demo only — nothing is actually charged or shipped)",
        "hi": "Claim ho gaya! (demo hai — kuch actually charge ya ship nahi hota)",
        "pa": "Claim ho gaya! (demo hai — kujh actually charge ya ship nahi hunda)",
    },
    "view_cart_response": {
        "en": "This is a demo bot, so there's no real cart to show — but in a live app this button would open it.",
        "hi": "Yeh demo bot hai, isliye dikhane ke liye real cart nahi hai — live app mein yeh button use khol deta.",
        "pa": "Eh demo bot hai, es layi vikhan layi real cart nahi hai — live app ch eh button ohnu khol denda.",
    },
    "not_interested_response": {
        "en": "Got it, noted — we'll back off on offers like this.",
        "hi": "Theek hai, note kar liya — hum aise offers kam bhejenge.",
        "pa": "Theek hai, note kar lia — asin ajihe offers ghat bhejange.",
    },
    "why_no_recent_decision": {
        "en": "No recent decision to explain yet — send /start first.",
        "hi": "Abhi explain karne ke liye koi recent decision nahi hai — pehle /start karein.",
        "pa": "Hale explain karan layi koi recent decision nahi hai — pehlan /start karo.",
    },
    "why_intro": {
        "en": "Here's why, in plain terms:",
        "hi": "Yeh raha simple karan:",
        "pa": "Eh riha sada karan:",
    },
    "simulate_help": {
        "en": (
            "Try: /simulate abandon_cart, /simulate go_inactive, or /simulate points_expiring "
            "— each one changes your demo profile and shows you the offer you'd get right now."
        ),
        "hi": (
            "Try karein: /simulate abandon_cart, /simulate go_inactive, ya /simulate points_expiring "
            "— har ek aapka demo profile badal ke abhi ka offer dikhata hai."
        ),
        "pa": (
            "Try karo: /simulate abandon_cart, /simulate go_inactive, ya /simulate points_expiring "
            "— har ik tuhada demo profile badal ke hun da offer vikhaunda hai."
        ),
    },
    "simulate_abandon_cart_intro": {
        "en": "Simulated: you just abandoned a cart. Here's what happens now —",
        "hi": "Simulate kiya: aapne abhi cart chhoda. Ab yeh hota hai —",
        "pa": "Simulate keeta: tusi hune cart chhadiya. Hun eh hunda hai —",
    },
    "simulate_go_inactive_intro": {
        "en": "Simulated: you've now been inactive for 45+ days. Here's what happens now —",
        "hi": "Simulate kiya: aap ab 45+ din se inactive hain. Ab yeh hota hai —",
        "pa": "Simulate keeta: tusi hun 45+ din ton inactive ho. Hun eh hunda hai —",
    },
    "simulate_points_expiring_intro": {
        "en": "Simulated: your reward points are about to expire. Here's what happens now —",
        "hi": "Simulate kiya: aapke reward points expire hone wale hain. Ab yeh hota hai —",
        "pa": "Simulate keeta: tuhade reward points expire hon wale ne. Hun eh hunda hai —",
    },
    "simulate_unknown": {
        "en": "Didn't recognise that scenario. {help}",
        "hi": "Yeh scenario samajh nahi aaya. {help}",
        "pa": "Eh scenario samajh nahi aaya. {help}",
    },
    "preferences_menu": {
        "en": "Your preferences — language: {language}, max offers/week: {frequency}.",
        "hi": "Aapki preferences — language: {language}, max offers/week: {frequency}.",
        "pa": "Tuhadiyan preferences — language: {language}, max offers/week: {frequency}.",
    },
    "preferences_language_button": {"en": "🌐 Change language", "hi": "🌐 Language badlein", "pa": "🌐 Language badlo"},
    "preferences_frequency_button": {"en": "📅 Change frequency", "hi": "📅 Frequency badlein", "pa": "📅 Frequency badlo"},
    "preferences_language_updated": {
        "en": "Language set to {language}.",
        "hi": "Language {language} set ho gayi.",
        "pa": "Language {language} set ho gayi.",
    },
    "preferences_frequency_updated": {
        "en": "Max offers/week set to {frequency}.",
        "hi": "Max offers/week {frequency} set ho gaya.",
        "pa": "Max offers/week {frequency} set ho gaya.",
    },
    "stop_confirm": {
        "en": "You're opted out — no more offers will be sent. Send /start to opt back in anytime.",
        "hi": "Aap opt-out ho gaye hain — ab koi offer nahi bheja jayega. Kabhi bhi /start se wapas opt-in karein.",
        "pa": "Tusi opt-out ho gaye ho — hun koi offer nahi bhejia jayega. Kadi vi /start naal wapas opt-in karo.",
    },
    "feedback_prompt": {
        "en": "Send your feedback as: /feedback your message here",
        "hi": "Apna feedback is tarah bhejein: /feedback aapka message yahan",
        "pa": "Apna feedback is tarah bhejo: /feedback tuhada message ithe",
    },
    "feedback_thanks": {
        "en": "Thanks for the feedback — noted!",
        "hi": "Feedback ke liye dhanyavaad — note kar liya!",
        "pa": "Feedback layi shukriya — note kar lia!",
    },
    "negotiation_blocked": {
        "en": "Thanks for asking — nothing more to offer right now though. Check back later!",
        "hi": "Poochne ke liye dhanyavaad — abhi aur kuch offer nahi hai. Baad mein dobara dekhein!",
        "pa": "Puchhan layi shukriya — hun hor kujh offer nahi hai. Baad ch dubara vekho!",
    },
    "rate_limited": {
        "en": "Slow down a little — try again in a few seconds.",
        "hi": "Thoda slow karein — kuch second mein phir try karein.",
        "pa": "Thoda slow karo — kujh second ch fer try karo.",
    },
    "generic_error": {
        "en": "Something went wrong on our end — please try again.",
        "hi": "Kuch galat ho gaya — kripya dobara try karein.",
        "pa": "Kujh galat ho gaya — kirpa karke dubara try karo.",
    },
}


def t(key: str, language: str, **kwargs) -> str:
    lang = language if language in SUPPORTED_LANGUAGES else "en"
    template = TRANSLATIONS[key].get(lang, TRANSLATIONS[key]["en"])
    return template.format(**kwargs) if kwargs else template
