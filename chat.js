/* PanelReady help chat (Nov 8, 2026): a free, scripted helper on every page of panelready.co. No AI service and
 * no keys: written answers (KB below) matched to what the visitor types, plus four actions through the signup
 * worker the site already uses:
 *   - start the free trial (POST /signup, the same as the form on the homepage; src "chat|...")
 *   - email a subscriber their account link (POST /link, the same as the account page)
 *   - live counts (GET /search?f=index, the same public counts as panelready.co/search/: no names or contacts)
 *   - pass a typed question to Matt (POST /ask; the PC's hourly run emails it to the PanelReady mailbox with
 *     Reply-To set to the visitor). If the worker can't take it, the visitor gets a ready-made email instead.
 * Loaded with <script src=".../chat.js" defer> from index.html and every page build_pages.py writes. Keep SPECS in
 * step with pr/specialty.py (tests/test_chat.py checks), and the answers in step with the homepage FAQ and pricing.
 */
(function () {
  "use strict";
  if (window.__panelreadyChat) return;
  window.__panelreadyChat = true;

  var W = "https://panelready-signup.matt-fixnotice.workers.dev";
  var MAIL = "matt@panelready.co";
  var me = document.currentScript;
  var ROOT = (function () { try { return new URL(".", me.src).href; } catch (e) { return "/"; } })();
  var REDUCE = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var STATES = {AL:"Alabama",AK:"Alaska",AZ:"Arizona",AR:"Arkansas",CA:"California",CO:"Colorado",CT:"Connecticut",DE:"Delaware",
    DC:"Washington, DC",FL:"Florida",GA:"Georgia",HI:"Hawaii",ID:"Idaho",IL:"Illinois",IN:"Indiana",IA:"Iowa",KS:"Kansas",KY:"Kentucky",
    LA:"Louisiana",ME:"Maine",MD:"Maryland",MA:"Massachusetts",MI:"Michigan",MN:"Minnesota",MS:"Mississippi",MO:"Missouri",MT:"Montana",
    NE:"Nebraska",NV:"Nevada",NH:"New Hampshire",NJ:"New Jersey",NM:"New Mexico",NY:"New York",NC:"North Carolina",ND:"North Dakota",
    OH:"Ohio",OK:"Oklahoma",OR:"Oregon",PA:"Pennsylvania",RI:"Rhode Island",SC:"South Carolina",SD:"South Dakota",TN:"Tennessee",
    TX:"Texas",UT:"Utah",VT:"Vermont",VA:"Virginia",WA:"Washington",WV:"West Virginia",WI:"Wisconsin",WY:"Wyoming"};
  var CATS = [["all", "Every category"], ["behavioral", "Behavioral health"], ["medical", "Medical practices & clinics"],
    ["dental", "Dental"], ["therapy", "Therapy & rehab"], ["home_senior", "Home care & senior living"],
    ["dme_transport", "DME, pharmacy & transport"]];
  var SPECS = /*SPECS*/[["residential","Residential treatment (psychiatric, youth, mental health, substance use)","behavioral"],["aba","ABA / behavior analysis","behavioral"],["substance_use","Substance use treatment","behavioral"],["psychiatry","Psychiatry & psychiatric NPs and nurses","behavioral"],["counseling","Counselors (LPC / LMHC)","behavioral"],["social_work","Clinical social workers","behavioral"],["psychology","Psychologists","behavioral"],["mft","Marriage & family therapists","behavioral"],["mh_clinics","Mental health clinics & agencies","behavioral"],["peer_chw","Peer specialists & community health workers","behavioral"],["community_health","Community health centers, FQHCs & rural health clinics","medical"],["urgent_care","Urgent care","medical"],["primary_care","Primary care (family, internal, NPs, PAs)","medical"],["pediatrics","Pediatrics","medical"],["womens_health","OB/GYN, midwives & women's health","medical"],["cardiology","Cardiology","medical"],["dermatology","Dermatology","medical"],["orthopedics","Orthopedics & sports medicine","medical"],["neurology","Neurology","medical"],["surgery","Surgery & surgery centers","medical"],["anesthesia","Anesthesia & pain","medical"],["imaging","Radiology & imaging","medical"],["labs","Labs","medical"],["dialysis","Dialysis","medical"],["ophthalmology","Ophthalmology","medical"],["schools","School-based services (LEAs)","medical"],["nursing","Nurse-owned practices (wound care, infusion, lactation)","medical"],["physical_therapy","Physical therapy","therapy"],["occupational_therapy","Occupational therapy","therapy"],["speech_hearing","Speech & hearing","therapy"],["rehab_clinics","Rehab clinics & practitioners","therapy"],["chiropractic","Chiropractic","therapy"],["podiatry","Podiatry","therapy"],["optometry","Optometry","therapy"],["dietitians","Dietitians & nutrition","therapy"],["acupuncture_massage","Acupuncture & massage","therapy"],["general_dentistry","General dentistry","dental"],["dental_specialists","Dental specialists (ortho, pediatric, oral surgery...)","dental"],["dental_hygiene","Dental hygienists","dental"],["home_health","Home health agencies","home_senior"],["hospice","Hospice","home_senior"],["home_care","Home care & aides","home_senior"],["residential_idd","IDD & disability services (group homes, day habilitation)","home_senior"],["senior_living","Nursing & assisted living facilities","home_senior"],["doulas","Doulas","home_senior"],["case_management","Case management & care coordination","home_senior"],["orthotics_prosthetics","Orthotics & prosthetics (O&P)","dme_transport"],["dme","DME & medical supplies","dme_transport"],["pharmacy","Pharmacies","dme_transport"],["transport","Medical transport","dme_transport"]];

  // ------------------------------------------------------------------ answers
  function L(path, text) { return '<a href="' + ROOT + path + '">' + text + "</a>"; }
  var KB = [
    {id: "what", t: "What is PanelReady?", k: ["what is panelready", "what is this", "what do you do", "what do you sell", "what is it", "who is it for", "how can this help", "panelready"],
     a: "PanelReady sends credentialing and medical billing companies a spreadsheet every week of the healthcare practices that just registered in their state: phone, address, the owner's name, a score and a ready-to-say opener for each. Brand-new practices need credentialing and billing set up, so you reach them before anyone else does.",
     r: ["how", "inlist", "trial"]},
    {id: "how", t: "How does it work?", k: ["how does it work", "how it works", "how do you get", "process", "where do the leads come from", "sorting"],
     a: "Every week CMS publishes the new registrations in the federal NPI registry: about 13,000 rows of providers, employees, students and practices mixed together. We keep the real practices and sole proprietors (about one row in three), sort them by state, category and specialty, add phones, owners, websites and a score, and email you the spreadsheet. " + L("#how", "See how it works"),
     r: ["source", "fresh", "inlist"]},
    {id: "source", t: "Where does the data come from?", k: ["data come from", "data source", "source", "nppes", "npi registry", "cms", "where do you get", "legit", "accurate"],
     a: "From NPPES, the National Plan and Provider Enumeration System run by CMS. Every provider and organization that bills must have an NPI, and CMS publishes the registry and weekly updates as public files. We read the weekly file; we don't change it or add to it.",
     r: ["fresh", "real", "hipaa"]},
    {id: "fresh", t: "How fresh are the lists?", k: ["fresh", "how new", "how old", "how recent", "up to date", "delay", "how quickly"],
     a: "CMS posts each week's file about a week after the week ends, and most registrations in it are one to six days old by then. So a practice is on your list one to two weeks after it registered, typically weeks before it has finished credentialing with its first payer.",
     r: ["when", "source"]},
    {id: "when", t: "When do the lists arrive?", k: ["when", "what day", "monday", "arrive", "schedule", "how often", "weekly", "every week", "frequency"],
     a: "Every week, usually Monday morning, as soon as that week's federal file is out. On the free trial your first list arrives within minutes of signing up and the second with the following week's file.",
     r: ["fresh", "notgot", "trial"]},
    {id: "real", t: "Are these real practices?", k: ["real practices", "just anyone", "employees", "individuals", "sole proprietor", "who is on the list", "filter", "junk"],
     a: "We keep organizations (practices, clinics, agencies, suppliers) and individuals who flagged themselves as sole proprietors. Employees registering for a new job, students and deactivated numbers are dropped. Roughly one row in three survives.",
     r: ["inlist", "kindnew"]},
    {id: "inlist", t: "What's in a list?", k: ["what's in", "whats in", "what is in", "what do i get", "columns", "fields", "included", "spreadsheet", "what does the list", "details", "information"],
     a: "Each weekly email has a spreadsheet (an overview, the Top 25 to call first with an opener for each, every new practice with phone, address, NPI, specialty and the owner's name, and a call script), a file that imports into HubSpot or Salesforce, and an outreach kit PDF. Organizations also get their website, email and Google rating where we can find them. " + L("#sample", "See a sample"),
     r: ["owner", "emails", "score", "sample"]},
    {id: "owner", t: "Do I get the owner's name and number?", k: ["owner", "decision maker", "direct line", "authorized official", "contact name", "who to call", "linkedin"],
     a: "Yes. Every practice has its owner or authorized official by name and title, with their own phone number when the registry lists one, plus a one-click LinkedIn search for them. Skip the front desk.",
     r: ["phones", "emails"]},
    {id: "phones", t: "Do the lists have phone numbers?", k: ["phone", "phone number", "phones", "call them", "telephone", "cold call"],
     a: "Yes: the phone and address each practice gave CMS, on every row, plus the owner's own number when the registry lists one. Each row also says how many providers share that phone, which tells a brand-new practice from an established office.",
     r: ["owner", "emails"]},
    {id: "emails", t: "Do I get email addresses?", k: ["email address", "emails", "email addresses", "do you have emails", "contact email"],
     a: "For organizations, where we can find one, on the free lists too. The registry has phones and addresses but no emails, so we look for each new organization's own website and add the website, email and Google rating we find; we never guess an address. Every email is marked as a person or a shared inbox (info@, office@) and checked that its domain takes mail. Sole proprietors rarely have a website yet, so their rows have the phone and address.",
     r: ["owner", "crm"]},
    {id: "score", t: "What's the score and the Top 25?", k: ["score", "top 25", "lead score", "priority", "best first", "ranking", "rank", "sorted"],
     a: "Every practice is scored 0 to 100 for how likely it needs credentialing and billing help soon, with the reason (including how many providers share its phone). The best 25 are marked and the list is sorted best-first, so you call the right ones first.",
     r: ["opener", "inlist"]},
    {id: "opener", t: "What's the opener and outreach kit?", k: ["opener", "script", "call script", "email template", "outreach kit", "what to say", "pitch"],
     a: "Every practice comes with a ready-to-say first line (name, city, when it registered, specialty). The outreach kit PDF has a call script, an email template and what every column means.",
     r: ["score", "crm"]},
    {id: "kindnew", t: "What does \"what kind of new\" mean?", k: ["kind of new", "brand new", "new location", "re-registration", "existing office", "days since"],
     a: "Each row says whether it's a brand-new practice, a new location of a larger organization (named when the registry names it), an owner opening several locations, an established office that just registered as a practice, or a re-registration, plus how many days ago it registered. Brand-new practices need everything set up from scratch.",
     r: ["real", "score"]},
    {id: "trial", t: "How does the free trial work?", k: ["free trial", "trial", "free lists", "try it", "try first", "two free", "2 free", "no card", "free"],
     a: "Your next two weekly lists are free: no card, no call. The first arrives within minutes, the second with the following week's federal file. Free lists have the weekly spreadsheet, the practices that moved or changed, the CRM file and the outreach kit; the 90-day history, monthly lists and account page come with a subscription. Afterwards you can subscribe, or do nothing and get a short free weekly digest until you say stop.",
     r: ["pricing"], go: "trial"},
    {id: "pricing", t: "How much does it cost?", k: ["price", "pricing", "cost", "how much", "plans", "plan", "rates", "fee", "charge", "expensive", "cheap", "monthly"],
     a: "<b>$49</b> your local area (5 to 100 miles of a ZIP) · <b>$89</b> one state, one category · <b>$149</b> one whole state (most billing companies) · <b>$199</b> three states · <b>$249</b> one specialty in every state · <b>$499</b> every state. All monthly; pay yearly and get 2 months free. Every plan includes the full weekly list, the last 90 days on day one, the monthly lists, Roster Watch, teammates and the 90-day guarantee. " + L("#pricing", "See pricing"),
     r: ["trial", "pay", "which"]},
    {id: "which", t: "Which plan should I pick?", k: ["which plan", "recommend", "best plan", "what plan", "right plan", "difference between plans", "compare plans"],
     a: "Most billing and credentialing companies take one whole state ($149). If you only serve one kind of practice in one state, one state and one category ($89) is enough; if you work near home, the local plan ($49) covers a radius around your ZIP. Firms that serve one specialty nationwide (ABA, residential treatment, FQHCs, O&amp;P...) take the one-specialty plan ($249), and national firms the every-state plan ($499). Not sure? Start with the two free lists.",
     r: ["pricing", "trial", "specialties"]},
    {id: "local", t: "Can I get just my local area?", k: ["local", "zip", "radius", "near me", "miles", "my area", "my city", "county", "metro"],
     a: "Yes. The local plan ($49 a month) covers every new practice within 5 to 100 miles of your ZIP code, every category. The free trial can be local too: on the " + L("#free", "trial form") + ", use a ZIP code and a radius instead of the whole state.",
     r: ["pricing", "states"]},
    {id: "states", t: "Which states do you cover?", k: ["which states", "what states", "states", "nationwide", "all states", "every state", "my state", "cover", "coverage", "territory", "more than one state", "multiple states"],
     a: "Every state plus DC. Plans cover your local area, one state, three states, or every state; the one-specialty plan covers one specialty in every state. " + L("states/", "See each state's numbers"),
     r: ["pricing", "local", "counts"]},
    {id: "specialties", t: "Can I get only certain specialties?", k: ["specialty", "specialties", "only aba", "only certain", "just one specialty", "filter by", "narrow", "aba", "psychiatry", "physical therapy", "home health", "fqhc", "orthotics", "prosthetics", "o&p", "residential"],
     a: "Yes. Pick one on the free-trial form, and subscribers can tick as many as they like on their account page: ABA, residential treatment, psychiatry, counselors, primary care, midwives, community health centers (FQHCs and rural health clinics), physical therapy, dental specialists, home health, DME, orthotics &amp; prosthetics and more, 50 in all. Serve one specialty across the country? The one-specialty plan covers it in every state for $249 a month.",
     r: ["categories", "trial", "counts"]},
    {id: "categories", t: "What are the six categories?", k: ["categories", "category", "six categories", "what kinds of practices", "types of practices", "practice types"],
     a: "Behavioral health (counselors, psychologists, psychiatry, ABA, residential treatment, substance use, peer specialists) · Medical practices &amp; clinics (physicians, NPs, PAs, midwives, community health centers and rural health clinics, urgent care, surgery centers) · Dental · Therapy &amp; rehab (PT, OT, speech, chiropractic, podiatry, optometry) · Home care &amp; senior living (home health, hospice, assisted living, IDD group homes, day habilitation) · DME, pharmacy &amp; transport (DME, orthotics &amp; prosthetics, pharmacies, medical transport, ambulance).",
     r: ["specialties", "counts"]},
    {id: "niche", t: "One specialty in every state ($249)", k: ["one specialty", "every state one", "nationwide specialty", "only residential", "niche", "249"],
     a: "The one-specialty plan ($249 a month) sends every new practice in one specialty, in every state, every week: for firms that serve one kind of practice nationwide (residential treatment centers, ABA, FQHCs and rural health clinics, orthotics &amp; prosthetics, home health...). Pick from 50 specialties and switch any time from your account page. It includes everything in the whole-state plan, you plus 4 teammates and Roster Watch for 500 providers.",
     r: ["specialties", "trial", "pricing"]},
    {id: "week", t: "Can I buy just one week?", k: ["one week", "one time", "one-time", "single list", "just this week", "39", "no subscription", "without subscribing"],
     a: "Yes: just this week's list for one state, every category, for $39 one time. Open your state's page and use the \"Just this week\" button; it's emailed to your PayPal address within minutes. " + L("states/", "Pick your state"),
     r: ["pricing", "trial"]},
    {id: "yearly", t: "Is there a yearly price?", k: ["yearly", "annual", "annually", "per year", "discount", "2 months free", "two months free", "coupon", "promo"],
     a: "Every plan can be paid yearly for the price of ten months (2 months free): flip the Monthly / Yearly switch in " + L("#pricing", "pricing") + ".",
     r: ["pricing", "pay"]},
    {id: "pay", t: "How do I subscribe and pay?", k: ["subscribe", "sign up for a plan", "buy", "purchase", "pay", "payment", "paypal", "credit card", "card", "checkout", "upgrade", "invoice", "charged", "billed", "when do i get charged"],
     a: "In " + L("#pricing", "Pricing") + ", pick a plan and use its PayPal button. Right after you pay, a short form asks which state (and category or specialty) to send; your first list, with the last 90 days, arrives within minutes. Payments go through PayPal and show as Avery Data Co., the company behind PanelReady.",
     r: ["avery", "cancel", "pricing"]},
    {id: "avery", t: "Who is Avery Data Co.?", k: ["avery", "avery data", "charge", "statement", "who are you", "company behind", "who runs", "who owns", "about"],
     a: "PanelReady's parent company: a New York business that builds subscription services from public data. It's the name PayPal shows at checkout and on your statement, so a charge from Avery Data Co. is your PanelReady subscription. " + L("about/", "About us"),
     r: ["pay", "contact"]},
    {id: "cancel", t: "How do I cancel?", k: ["cancel", "cancellation", "stop my subscription", "end subscription", "quit", "unsubscribe from plan", "contract", "commitment", "lock in"],
     a: "Any time, in your PayPal account under Subscriptions: your lists and account page continue to the end of the period you've paid for. Or reply STOP to any email and we cancel the PayPal subscription for you. No contracts, no calls, no forms.",
     r: ["guarantee", "stop"]},
    {id: "stop", t: "How do I stop the emails?", k: ["stop emails", "unsubscribe", "stop sending", "remove me", "opt out", "too many emails"],
     a: "Reply STOP to any of our emails and they stop right away (and any PayPal subscription is cancelled for you).",
     r: ["cancel"]},
    {id: "guarantee", t: "How does the guarantee work?", k: ["guarantee", "refund", "money back", "risk", "no results", "doesn't work", "what if"],
     a: "If you don't sign at least one new client from your PanelReady lists during your first 90 days as a paying subscriber, reply to any of our emails and tell us: your next 3 months are free (we pause your PayPal subscription for three months). One per company; no forms, no proof required. For anything else about a charge, ask Matt.",
     r: ["cancel", "ask"]},
    {id: "exclusive", t: "Is my list exclusive?", k: ["exclusive", "shared", "other companies", "competitors", "same list", "who else", "resell"],
     a: "No. PanelReady is a data subscription, not an exclusive-lead service: the Texas behavioral-health list is the same for every company that subscribes to it. A state produces far more new practices each week than any one firm can call, and what you pay for is being weeks ahead of everyone who isn't on the list. Need a state and category reserved for your company alone? That's a separate arrangement: ask Matt.",
     r: ["ask", "pricing"]},
    {id: "history", t: "Do I get past weeks?", k: ["90 days", "history", "past weeks", "backfill", "older", "previous weeks", "last 90"],
     a: "Yes, with a subscription: your first paid list includes the last 90 days of new practices in your territory, and your account page keeps past weeks to download.",
     r: ["account", "pay"]},
    {id: "stuck", t: "What's the stuck-in-credentialing list?", k: ["stuck", "stuck in credentialing", "stalled", "not enrolled", "medicare enrollment"],
     a: "Once a month, subscribers also get the practices in their state that registered 2 to 12 months ago, in specialties where most new practices enroll with Medicare, and still aren't on Medicare's public enrollment list. Months in, they can't bill Medicare yet, which usually means credentialing hasn't started or has stalled. Treat it as \"likely\", not certain.",
     r: ["reval", "planchanges"]},
    {id: "reval", t: "What are the revalidation and moved lists?", k: ["revalidation", "revalidate", "moved", "practice moved", "relocated", "address change", "changed practices"],
     a: "Every Medicare provider has to revalidate every few years, and CMS publishes the due dates: once a month you get the practices in your territory due in the next six months or overdue, soonest first. Every week you also get practices whose location changed; each has to update its address with Medicare and every plan. Both are established practices that already bill.",
     r: ["stuck", "planchanges"]},
    {id: "planchanges", t: "What's the plan-changes list?", k: ["plan changes", "plan-change", "medicare advantage", "medicaid plans", "insurer leaving", "plan exit"],
     a: "When an insurer stops offering Medicare Advantage in a county, or a state changes its Medicaid plans, those patients have to pick new plans, and their practices need contracts and credentialing with the plans they move to. While a change is coming, every plan (free trial included) gets those practices in its territory once a month.",
     r: ["stuck", "reval"]},
    {id: "team", t: "Can my team get the lists?", k: ["team", "teammates", "colleague", "coworker", "add users", "more users", "cc", "share with"],
     a: "Yes. Add teammates on your account page and each gets a copy of every list email: 1 on the local plan, 2 on one state and one category, 4 on the whole-state and one-specialty plans, 9 on three states and 14 on every state.",
     r: ["account", "pricing"]},
    {id: "roster", t: "What's Roster Watch?", k: ["roster", "roster watch", "my providers", "existing clients", "oig", "exclusion", "monitor", "opt-out", "deactivation"],
     a: "Give us the NPIs of the providers you already work for. Every week we check each against the OIG exclusion list, Medicare opt-outs, NPI deactivations, revalidation due dates, Medicare enrollment and pending applications, and its registered address, and your weekly email tells you what changed. Up to 100, 500, 2,000 or 5,000 providers depending on the plan.",
     r: ["team", "account"]},
    {id: "crm", t: "Does it work with my CRM?", k: ["crm", "hubspot", "salesforce", "zapier", "make.com", "webhook", "import", "integration", "api", "csv", "excel"],
     a: "Every email has a file that imports straight into HubSpot or Salesforce, and the spreadsheet opens in Excel or Google Sheets. Or paste a webhook address (Zapier, Make or your own) on your account page and every list is sent to it as JSON the moment it goes out.",
     r: ["inlist", "account"]},
    {id: "account", t: "Where's my account page?", k: ["account page", "account", "my account", "login", "log in", "sign in", "password", "dashboard", "portal"],
     a: "Subscribers have an account page for past weeks, territory, specialties, teammates, Roster Watch and the webhook. There's no password: every list email carries your private link, or I can email it to you. On the free trial your lists come by email; the account page opens once you subscribe.",
     r: ["history", "change"], go: "link"},
    {id: "change", t: "How do I change my state or category?", k: ["change state", "change my state", "change category", "switch", "change territory", "different state", "update my", "wrong state", "add a state", "change specialty"],
     a: "Subscribers change it any time on their account page (it applies from the next list). On the free trial, reply to any list email with what you'd like and Matt will switch it.",
     r: ["account", "pricing"]},
    {id: "notgot", t: "I didn't get my list", k: ["didn't get", "did not get", "didnt get", "not received", "haven't received", "no email", "where is my list", "missing", "spam", "not arrive", "never got"],
     a: "The first free list goes out within minutes of signing up, then weekly. Check your spam or promotions folder for mail from matt@panelready.co, and add it to your contacts. Still nothing after an hour? Tell Matt and he'll resend it.",
     r: ["ask"]},
    {id: "sample", t: "Can I see a sample?", k: ["sample", "example", "demo", "see a list", "preview", "screenshot", "show me"],
     a: "Yes: " + L("#sample", "real rows from a recent New York list") + " (phones masked) and a full sample spreadsheet to download are on the homepage. Or start the free trial and get your own state's list in minutes.",
     r: ["inlist", "trial"]},
    {id: "search", t: "Is there a way to look up counts?", k: ["live search", "search page", "look up", "lookup", "by county", "by zip", "how many in"],
     a: "Yes: the free " + L("search/", "live search") + " shows new practices by state, county, metro, city, ZIP radius, specialty and type for the last 13 weeks, plus practices stuck in credentialing and revalidations due. No names or contacts. Or ask me, e.g. \"how many new ABA practices in Texas?\"",
     r: ["states"], go: "counts"},
    {id: "hipaa", t: "Is this data legal to use? HIPAA?", k: ["hipaa", "legal", "allowed", "privacy", "compliant", "patient data", "public data", "tcpa", "can-spam"],
     a: "The NPI registry is a public business directory CMS publishes for anyone to download; it has no patient information. Contacting the businesses on it is ordinary B2B outreach, but how you call or email them is up to you to keep within the rules that apply to you (I'm not a lawyer). " + L("privacy/", "Our privacy policy"),
     r: ["source"]},
    {id: "volume", t: "How many new practices are there each week?", k: ["how many leads", "how many practices", "volume", "per week", "per month", "enough leads", "worth it"],
     a: "Across the country, about 4,000 to 5,000 practices and sole proprietors a week after filtering; a big state like New York or Texas has a couple hundred. Ask me for a state or specialty (\"how many new PT practices in Florida?\") and I'll look up the latest week.",
     r: ["states"], go: "counts"},
    {id: "contact", t: "How do I contact you?", k: ["contact", "talk to", "speak to", "human", "real person", "phone number for you", "call you", "email you", "support", "help me", "matt"],
     a: "Email " + '<a href="mailto:' + MAIL + '">' + MAIL + "</a>, or type your question here and I'll pass it to Matt; he replies by email.",
     r: [], go: "ask"},
  ];
  var BY = {};
  KB.forEach(function (e) { BY[e.id] = e; });

  // ------------------------------------------------------------------ matching
  var STOP = {"a":1,"an":1,"the":1,"i":1,"me":1,"my":1,"you":1,"your":1,"we":1,"our":1,"is":1,"are":1,"do":1,"does":1,"can":1,"to":1,"of":1,
    "for":1,"in":1,"on":1,"it":1,"and":1,"or":1,"what":1,"how":1,"if":1,"be":1,"get":1,"with":1,"this":1,"that":1,"there":1,"any":1,"have":1};
  function norm(s) { return " " + String(s || "").toLowerCase().replace(/[’']/g, "'").replace(/[^a-z0-9&'@.\s-]/g, " ").replace(/\s+/g, " ").trim() + " "; }
  function words(s) { return norm(s).trim().split(" ").filter(function (w) { return w && !STOP[w]; }); }
  function score(e, text) {
    var n = norm(text), s = 0;
    e.k.forEach(function (k) {
      var multi = k.indexOf(" ") > 0;
      if (n.indexOf(" " + k + " ") >= 0 || (!multi && (n.indexOf(" " + k + "s ") >= 0 || n.indexOf(" " + k + "es ") >= 0))) s += multi ? 3 + k.split(" ").length * 0.5 : 2;
      else if (k.length > 5 && n.indexOf(k) >= 0) s += 1;
    });
    var tw = words(e.t), uw = words(text);
    uw.forEach(function (w) { if (w.length > 2 && tw.indexOf(w) >= 0) s += 0.6; });
    return s;
  }
  function best(text) {
    return KB.map(function (e) { return {e: e, s: score(e, text)}; }).sort(function (a, b) { return b.s - a.s; });
  }

  // states and specialties in free text (for counts and the trial)
  var STATE_NAMES = Object.keys(STATES).filter(function (k) { return k !== "DC"; }).map(function (k) { return [STATES[k].toLowerCase(), k]; })
    .concat([["washington dc", "DC"], ["washington d.c.", "DC"], ["d.c.", "DC"], ["district of columbia", "DC"]])
    .sort(function (a, b) { return b[0].length - a[0].length; });
  var AMBIGUOUS = {OK: 1, IN: 1, ME: 1, OR: 1, HI: 1};       // also ordinary words when typed in capitals
  function findState(raw) {
    var n = norm(raw);
    for (var i = 0; i < STATE_NAMES.length; i++) {
      var nm = STATE_NAMES[i][0];
      if (nm === "washington" && / washington dc /.test(n)) continue;
      if (n.indexOf(" " + nm + " ") >= 0) return STATE_NAMES[i][1];
    }
    var t = String(raw || "").trim().replace(/[.!?]+$/, "").toUpperCase();
    if (STATES[t]) return t;
    var m = (String(raw || "").match(/\b([A-Z]{2})\b/g) || []).filter(function (c) { return STATES[c]; });
    var clear = m.filter(function (c) { return !AMBIGUOUS[c]; });
    if (clear.length) return clear[0];
    var near = String(raw || "").match(/\b(?:in|for|state of)\s+([A-Z]{2})\b/);
    return near && STATES[near[1]] ? near[1] : "";
  }
  // what a visitor might call a specialty -> [what to call it, a test on the federal specialty name]
  var TOPICS = [
    [/\b(aba|behavior(al)? analy\w*|autism)\b/, "ABA practices", /behavior analyst|behavioral analyst/i, "", "aba"],
    [/\b(residential|rtc|treatment cent(er|re)s?)\b/, "residential treatment facilities", /residential treatment/i, "", "residential"],
    [/\b(substance|addiction|rehab facilit\w*|detox|sud)\b/, "substance use treatment providers", /substance|addiction/i, "", "substance_use"],
    [/\b(psychiatr\w*|pmhnp)\b/, "psychiatry practices", /psychiatr/i, "", "psychiatry"],
    [/\b(counsel\w*|lpc|lmhc|therapists? \(mental\)|mental health counsel\w*)\b/, "counselors", /counselor/i, "", "counseling"],
    [/\b(social work\w*|lcsw|lmsw)\b/, "social workers", /social worker/i, "", "social_work"],
    [/\b(psycholog\w*)\b/, "psychologists", /psycholog/i, "", "psychology"],
    [/\b(marriage|mft|lmft|family therap\w*)\b/, "marriage & family therapists", /marriage/i, "", "mft"],
    [/\b(fqhcs?|rhcs?|community health cent\w*|rural health)\b/, "community health centers and rural health clinics", /federally qualified|rural health|community health clinic/i, "", "community_health"],
    [/\b(o&p|o & p|orthotic\w*|prosthetic\w*|orthotist\w*|prosthetist\w*)\b/, "orthotics & prosthetics practices", /orthot|prosthet|pedorth/i, "", "orthotics_prosthetics"],
    [/\b(physical therap\w*|pts?|dpt)\b/, "physical therapy practices", /physical therap/i, "", "physical_therapy"],
    [/\b(occupational therap\w*|ots?)\b/, "occupational therapy practices", /occupational therap/i, "", "occupational_therapy"],
    [/\b(speech|slps?|audiolog\w*)\b/, "speech and hearing practices", /speech|audiolog/i, "", "speech_hearing"],
    [/\b(chiro\w*)\b/, "chiropractors", /chiropract/i, "", "chiropractic"],
    [/\b(podiatr\w*)\b/, "podiatrists", /podiatr/i, "", "podiatry"],
    [/\b(optometr\w*)\b/, "optometrists", /optometr/i, "", "optometry"],
    [/\b(home health)\b/, "home health agencies", /home health/i, "", "home_health"],
    [/\b(hospice)\b/, "hospices", /hospice/i, "", "hospice"],
    [/\b(assisted living|nursing home|nursing facilit\w*|snf)\b/, "nursing and assisted living facilities", /assisted living|nursing facility|skilled nursing|nursing home/i, "", "senior_living"],
    [/\b(dme|durable medical|medical suppl\w*)\b/, "DME suppliers", /dme|durable|medical supply|medical equipment/i, "", "dme"],
    [/\b(pharmac\w*)\b/, "pharmacies", /pharmac/i, "", "pharmacy"],
    [/\b(ambulance|nemt|medical transport\w*|transportation)\b/, "medical transport companies", /ambulance|transport/i, "", "transport"],
    [/\b(urgent care)\b/, "urgent care centers", /urgent care/i, "", "urgent_care"],
    [/\b(nurse practitioners?|nps?)\b/, "nurse practitioners", /nurse practitioner/i, "medical"],
    [/\b(midwi\w*)\b/, "midwives", /midwi/i, "", "womens_health"],
    [/\b(dentists?|dental)\b/, "dental practices", null, "dental"],
    [/\b(behavioral health|mental health)\b/, "behavioral health practices", null, "behavioral"],
    [/\b(medical|physicians?|doctors?|clinics?)\b/, "medical practices & clinics", null, "medical"],
    [/\b(therapy and rehab|therapy & rehab|rehab)\b/, "therapy & rehab practices", null, "therapy"],
    [/\b(home care|senior)\b/, "home care & senior living providers", null, "home_senior"],
  ];
  function findTopic(raw) {
    var n = norm(raw);
    for (var i = 0; i < TOPICS.length; i++) if (TOPICS[i][0].test(n)) {
      var key = TOPICS[i][4] || "", g = SPECS.filter(function (s) { return s[0] === key; })[0];
      return {name: TOPICS[i][1], rx: TOPICS[i][2], cat: TOPICS[i][3] || (g ? g[2] : ""), key: key};
    }
    return null;
  }

  // ------------------------------------------------------------------ the widget
  var CSS = "" +
    ".prc-root{--prc-ink:#0f2340;--prc-teal:#0e7c7b;--prc-line:#e3e8ef;--prc-muted:#5b6b82;--prc-bg:#f6f8fb;--prc-over:cubic-bezier(.34,1.3,.64,1);--prc-ease:cubic-bezier(.2,.8,.2,1);" +
    "position:fixed;right:20px;bottom:20px;z-index:60;font:15px/1.5 Inter,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#334155}" +
    ".prc-root *{box-sizing:border-box}" +
    ".prc-launch{display:flex;align-items:center;gap:10px;border:0;background:none;padding:0;cursor:pointer;font:inherit}" +
    ".prc-pill{background:#fff;color:var(--prc-ink);font-weight:600;font-size:14px;padding:9px 14px;border-radius:999px;border:1px solid var(--prc-line);box-shadow:0 6px 18px -8px rgba(15,35,64,.35);transition:opacity .25s var(--prc-ease),transform .25s var(--prc-ease)}" +
    ".prc-dot{width:56px;height:56px;border-radius:50%;background:var(--prc-ink);display:grid;place-items:center;box-shadow:0 10px 26px -8px rgba(15,35,64,.55);transition:transform .35s var(--prc-over),box-shadow .2s}" +
    ".prc-dot svg{width:26px;height:26px}" +
    ".prc-launch:hover .prc-dot{transform:translateY(-2px) scale(1.04);box-shadow:0 14px 30px -8px rgba(15,35,64,.6)}" +
    ".prc-launch:active .prc-dot{transform:scale(.9,.84);transition-duration:.08s}" +           /* anticipation + squash */
    ".prc-launch:focus-visible{outline:none}.prc-launch:focus-visible .prc-dot{outline:3px solid #2dd4bf;outline-offset:3px}" +
    ".prc-root.open .prc-launch{opacity:0;pointer-events:none;transform:scale(.6);transition:opacity .15s,transform .2s ease-in}" +
    ".prc-hop .prc-dot{animation:prc-hop 1.1s var(--prc-ease) 1}" +
    "@keyframes prc-hop{0%{transform:none}14%{transform:scale(1.06,.9)}34%{transform:translateY(-12px) scale(.95,1.07)}56%{transform:translateY(0) scale(1.07,.92)}72%{transform:translateY(-3px) scale(.99,1.02)}100%{transform:none}}" +
    ".prc-panel{position:absolute;right:0;bottom:0;width:380px;height:min(600px,calc(100vh - 40px));background:#fff;border:1px solid var(--prc-line);border-radius:18px;" +
    "box-shadow:0 1px 2px rgba(15,35,64,.06),0 28px 60px -18px rgba(15,35,64,.4);display:flex;flex-direction:column;overflow:hidden;" +
    "transform-origin:calc(100% - 28px) calc(100% - 28px);opacity:0;transform:scale(.4) translateY(10px);pointer-events:none;visibility:hidden;" +
    "transition:opacity .16s ease-in,transform .2s ease-in,visibility 0s .2s}" +
    ".prc-root.open .prc-panel{opacity:1;transform:none;pointer-events:auto;visibility:visible;transition:opacity .2s var(--prc-ease),transform .42s var(--prc-over),visibility 0s}" +
    ".prc-head{display:flex;align-items:center;gap:10px;padding:14px 14px 14px 16px;background:var(--prc-ink);color:#fff}" +
    ".prc-head svg{width:30px;height:30px;flex:none}.prc-head b{display:block;font-size:15px}.prc-head span{display:block;font-size:12px;opacity:.75}" +
    ".prc-x{margin-left:auto;width:34px;height:34px;border-radius:10px;border:0;background:rgba(255,255,255,.1);color:#fff;font-size:20px;line-height:1;cursor:pointer}" +
    ".prc-x:hover{background:rgba(255,255,255,.2)}.prc-x:focus-visible{outline:2px solid #2dd4bf}" +
    ".prc-log{flex:1;overflow-y:auto;padding:16px 14px 6px;background:var(--prc-bg);scroll-behavior:smooth}" +
    ".prc-m{max-width:88%;margin:0 0 10px;padding:10px 13px;border-radius:14px;font-size:14.5px;line-height:1.5;word-wrap:break-word;animation:prc-in .32s var(--prc-ease) both}" +
    ".prc-bot{background:#fff;border:1px solid var(--prc-line);border-bottom-left-radius:5px;color:#334155}" +
    ".prc-me{margin-left:auto;background:var(--prc-ink);color:#fff;border-bottom-right-radius:5px;white-space:pre-wrap}" +
    ".prc-bot a{color:var(--prc-teal);font-weight:600}.prc-bot b{color:var(--prc-ink)}" +
    ".prc-bot .prc-big{display:block;font:700 26px/1.1 'Source Serif 4',Georgia,serif;color:var(--prc-ink);margin:2px 0 4px}" +
    "@keyframes prc-in{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:none}}" +
    ".prc-typing{display:inline-flex;gap:4px;padding:12px 14px}.prc-typing i{width:7px;height:7px;border-radius:50%;background:#9aa7b8;animation:prc-bob 1s var(--prc-ease) infinite}" +
    ".prc-typing i:nth-child(2){animation-delay:.15s}.prc-typing i:nth-child(3){animation-delay:.3s}" +
    "@keyframes prc-bob{0%,60%,100%{transform:none;opacity:.55}30%{transform:translateY(-5px);opacity:1}}" +
    ".prc-chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px;animation:prc-in .32s var(--prc-ease) .08s both}" +
    ".prc-chip{border:1px solid #b9d6d5;background:#fff;color:var(--prc-teal);font:600 13px/1.2 Inter,system-ui,sans-serif;padding:7px 11px;border-radius:999px;cursor:pointer;transition:transform .18s var(--prc-over),background .15s}" +
    ".prc-chip:hover{background:#eef7f6;transform:translateY(-1px)}.prc-chip:active{transform:scale(.96)}.prc-chip:focus-visible{outline:2px solid var(--prc-teal);outline-offset:2px}" +
    ".prc-chip.ghost{border-color:var(--prc-line);color:var(--prc-muted)}" +
    ".prc-form{display:flex;gap:8px;align-items:flex-end;padding:10px 12px 12px;border-top:1px solid var(--prc-line);background:#fff}" +
    ".prc-in{flex:1;resize:none;max-height:110px;min-height:42px;border:1px solid var(--prc-line);border-radius:12px;padding:10px 12px;font:15px/1.4 Inter,system-ui,sans-serif;color:var(--prc-ink);background:#fff}" +
    ".prc-in:focus{outline:none;border-color:var(--prc-teal);box-shadow:0 0 0 3px rgba(14,124,123,.15)}" +
    ".prc-send{width:42px;height:42px;flex:none;border:0;border-radius:12px;background:var(--prc-teal);color:#fff;cursor:pointer;display:grid;place-items:center;transition:transform .2s var(--prc-over),background .15s}" +
    ".prc-send:hover{background:#0a6362}.prc-send:active{transform:scale(.9)}.prc-send svg{width:18px;height:18px}" +
    ".prc-note{padding:0 14px 10px;background:#fff;font-size:11.5px;color:#8a97a9}" +
    ".prc-hp{position:absolute;left:-9999px;width:1px;height:1px;opacity:0}" +
    "@media (max-width:600px){.prc-root{right:14px;bottom:14px}.prc-pill{display:none}.prc-root.open{left:0;right:0;top:0;bottom:0}" +
    ".prc-root.open .prc-panel{position:fixed;inset:0;width:auto;height:100%;border-radius:0;border:0}.prc-root.open .prc-launch{display:none}.prc-in{font-size:16px}}" +
    "@media (prefers-reduced-motion:reduce){.prc-root *{animation:none!important;transition:none!important}}";

  var ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/><path d="M8.5 12h.01M12 12h.01M15.5 12h.01" stroke-width="2.6"/></svg>';
  var LOGO = '<svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="15" fill="#fff"/><rect x="18" y="17" width="28" height="32" rx="4" fill="none" stroke="#0f2340" stroke-width="4.5" stroke-linejoin="round"/><rect x="25" y="13" width="14" height="8" rx="2.5" fill="#0f2340"/><path d="M25 34l5.5 5.5L40 29" fill="none" stroke="#0e7c7b" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var SEND = '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';

  var root, log, input, panel, started = false, flow = null, busy = false;

  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function scroll() { log.scrollTop = log.scrollHeight; }

  function build() {
    var st = el("style"); st.textContent = CSS; document.head.appendChild(st);
    root = el("div", "prc-root");
    var launch = el("button", "prc-launch", '<span class="prc-pill">Questions? Ask here</span><span class="prc-dot">' + ICON + "</span>");
    launch.type = "button"; launch.setAttribute("aria-label", "Open the PanelReady help chat"); launch.setAttribute("aria-expanded", "false");
    panel = el("div", "prc-panel");
    panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "PanelReady help"); panel.setAttribute("aria-modal", "false");
    var head = el("div", "prc-head", LOGO + '<div><b>PanelReady help</b><span>Answers right away · Matt replies by email</span></div>');
    var x = el("button", "prc-x", "&times;"); x.type = "button"; x.setAttribute("aria-label", "Close the help chat");
    head.appendChild(x);
    log = el("div", "prc-log"); log.setAttribute("aria-live", "polite");
    var form = el("form", "prc-form");
    input = el("textarea", "prc-in"); input.rows = 1; input.placeholder = "Type your question…"; input.setAttribute("aria-label", "Your message");
    input.maxLength = 2000;
    var send = el("button", "prc-send", SEND); send.type = "submit"; send.setAttribute("aria-label", "Send");
    var hp = el("input", "prc-hp"); hp.name = "website"; hp.tabIndex = -1; hp.setAttribute("autocomplete", "off"); hp.setAttribute("aria-hidden", "true");
    form.appendChild(hp); form.appendChild(input); form.appendChild(send);
    panel.appendChild(head); panel.appendChild(log); panel.appendChild(form);
    panel.appendChild(el("div", "prc-note", "Questions you send to Matt go by email. " + '<a href="' + ROOT + 'privacy/" style="color:inherit">Privacy</a>'));
    root.appendChild(panel); root.appendChild(launch);
    document.body.appendChild(root);

    launch.onclick = function () { open(true); };
    x.onclick = function () { open(false); launch.focus(); };
    root.addEventListener("keydown", function (e) { if (e.key === "Escape" && root.classList.contains("open")) { open(false); launch.focus(); } });
    form.onsubmit = function (e) { e.preventDefault(); submit(hp.value); };
    input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(hp.value); } });
    input.addEventListener("input", function () { input.style.height = "auto"; input.style.height = Math.min(110, input.scrollHeight) + "px"; });

    // one small hop to say it's there (staged once per visit, after the visitor has had time to read)
    if (!REDUCE && !seen("hop")) setTimeout(function () { if (!root.classList.contains("open")) { launch.classList.add("prc-hop"); remember("hop"); } }, 9000);
  }
  function seen(k) { try { return sessionStorage.getItem("prc-" + k) === "1"; } catch (e) { return false; } }
  function remember(k) { try { sessionStorage.setItem("prc-" + k, "1"); } catch (e) {} }

  function open(on) {
    root.classList.toggle("open", on);
    root.querySelector(".prc-launch").setAttribute("aria-expanded", on ? "true" : "false");
    if (on) {
      if (!started) { started = true; greet(); }
      setTimeout(function () { input.focus(); }, REDUCE ? 0 : 250);
    }
  }

  function say(html, chips, delay) {
    // a short "typing" beat first (timing: longer answers take a little longer), then the message and its chips
    var t = el("div", "prc-m prc-bot prc-typing", "<i></i><i></i><i></i>");
    log.appendChild(t); scroll();
    var wait = REDUCE ? 0 : (delay != null ? delay : Math.min(900, 280 + String(html).length * 2));
    return new Promise(function (res) {
      setTimeout(function () {
        t.remove();
        log.appendChild(el("div", "prc-m prc-bot", html));
        if (chips && chips.length) {
          var row = el("div", "prc-chips");
          chips.forEach(function (c) {
            var b = el("button", "prc-chip" + (c.ghost ? " ghost" : ""), esc(c.label)); b.type = "button";
            b.onclick = function () { row.remove(); you(c.label); c.go(); };
            row.appendChild(b);
          });
          log.appendChild(row);
        }
        scroll(); res();
      }, wait);
    });
  }
  function you(text) { log.appendChild(el("div", "prc-m prc-me", esc(text))); scroll(); }
  function chip(label, go, ghost) { return {label: label, go: go, ghost: ghost}; }
  function plural(n, w) { return n.toLocaleString("en-US") + " " + w + (n === 1 ? "" : "s"); }

  var MENU = function () {
    return [chip("How does it work?", function () { answer(BY.how); }), chip("Pricing", function () { answer(BY.pricing); }),
      chip("Start my free trial", startTrial), chip("What's in a list?", function () { answer(BY.inlist); }),
      chip("Live counts", function () { startCounts(""); }), chip("Email me my account link", startLink),
      chip("Ask Matt a question", function () { startAsk(""); })];
  };
  function greet() {
    say("Hi! I can answer questions about PanelReady's weekly lists, plans and your account, start your two free lists, look up how many new practices registered, or pass a question to Matt. What can I help with?", MENU(), 350);
  }

  function setPlaceholder(t) { input.placeholder = t || "Type your question…"; }
  function cancelChip() { return chip("Cancel", function () { flow = null; setPlaceholder(); say("No problem. Anything else?", MENU()); }, true); }

  function answer(e) {
    var chips = (e.r || []).map(function (id) { return BY[id]; }).filter(Boolean).slice(0, 3)
      .map(function (r) { return chip(r.t, function () { answer(r); }); });
    if (e.go === "trial") chips.unshift(chip("Start my free trial", startTrial));
    if (e.go === "link") chips.unshift(chip("Email me my account link", startLink));
    if (e.go === "counts") chips.unshift(chip("Look up counts", function () { startCounts(""); }));
    if (e.go === "ask") chips.unshift(chip("Ask Matt a question", function () { startAsk(""); }));
    else if (e.id !== "trial" && e.id !== "pricing") chips.push(chip("Something else", function () { say("Sure: type your question, or pick one:", MENU()); }, true));
    return say(e.a, chips.slice(0, 5));
  }

  // ------------------------------------------------------------------ what the visitor typed
  function submit(honey) {
    var text = input.value.trim();
    if (!text || busy) return;
    input.value = ""; input.style.height = "auto";
    var chips = log.querySelectorAll(".prc-chips"); if (chips.length) chips[chips.length - 1].remove();
    you(text);
    if (flow) return step(text, honey);
    route(text);
  }

  function route(text) {
    var n = norm(text);
    if (/^ (hi|hello|hey|yo|good (morning|afternoon|evening)|thanks?|thank you|ty|ok|okay|cool|great) [!. ]*$/.test(n))
      return say(/thank|ty/.test(n) ? "You're welcome! Anything else?" : "Hi! What can I help you with?", MENU());
    if (/ (talk|speak|chat) (to|with) | (human|real person|representative) | (call|email|contact) (you|matt|someone|support) /.test(n))
      return startAsk(/\?$/.test(text) && text.length > 25 ? text : "");
    if (/ (start|begin|sign me up|sign up for (the |a )?(free )?trial|signup for (the |a )?trial|try it|get (my |the )?(two |2 )?free lists?|i want (the |a )?(free )?trial|free trial please) /.test(n)
        && !/ (how|what|does|is|cost|price) /.test(n))
      return startTrial();
    if (/ (send|email|resend|lost|forgot|need|get) .*(link|log ?in|sign ?in)|can'?t (log|sign) ?in|account link /.test(n))
      return startLink();
    if (/ (how many|number of|counts?|stats|statistics|volume of) /.test(n) && (findState(text) || findTopic(text) || / (nationwide|country|usa|u\.s\.|all states|every state) /.test(n)))
      return counts(findState(text), findTopic(text), / (nationwide|country|us|u\.s\.|usa|all states|every state) /.test(n));
    var topic = findTopic(text), b = best(text);
    if (topic && (/ (do you (have|cover|include|sell|offer)|can i get|leads? (for|on)|lists? (of|for)|include|covered|interested in|looking for|i (sell|bill|work) (to|for|with)) /.test(n) || b[0].s < 2))
      return coverage(topic, findState(text));
    if (b[0].s >= 2) {
      var e = b[0].e;
      if (b[0].s < 5 && words(text).length >= 6)           // a long question that only half matches: offer Matt too
        return answer(e).then(function () {
          return say("Not quite what you asked?", [chip("Send my question to Matt", function () { startAsk(text); })], 200);
        });
      return answer(e).then(function () {
        if (b[1] && b[1].s >= 3 && b[1].s >= b[0].s - 1 && b[1].e.id !== e.id && (e.r || []).indexOf(b[1].e.id) < 0)
          return say("You might also mean:", [chip(b[1].e.t, function () { answer(b[1].e); })], 200);
      });
    }
    return say("I don't have a written answer for that one. Want me to send it to Matt? He'll reply by email.",
      [chip("Yes, send it to Matt", function () { startAsk(text); }), chip("Show me the menu", function () { say("Here's what I can help with:", MENU()); }, true)]);
  }

  // ------------------------------------------------------------------ flows
  function step(text, honey) {
    var f = flow, n = norm(text);
    if (/^ (cancel|stop|never ?mind|quit|exit|back|menu) $/.test(n)) { flow = null; setPlaceholder(); return say("No problem. Anything else?", MENU()); }
    if (f.type === "trial") return trialStep(f, text);
    if (f.type === "link") return linkStep(f, text, honey);
    if (f.type === "ask") return askStep(f, text, honey);
    if (f.type === "counts") return countsStep(f, text);
  }
  var EMAIL = /^[^\s@<>,;]+@[^\s@<>,;]+\.[a-z]{2,}$/i;

  // free trial: email, company, state, category, specialty (optional), then the same signup as the homepage form
  function startTrial() {
    flow = {type: "trial", step: "email", d: {}};
    setPlaceholder("you@yourcompany.com");
    return say("Great: your next two weekly lists are free, no card. What's your work email?", [cancelChip()]);
  }
  function trialStep(f, text) {
    var d = f.d;
    if (f.step === "email") {
      if (!EMAIL.test(text)) return say("That doesn't look like an email address. What's your work email?", [cancelChip()]);
      d.email = text.toLowerCase(); f.step = "company"; setPlaceholder("Company name");
      return say("Thanks. What's your company called?", [cancelChip()]);
    }
    if (f.step === "company") {
      d.company = text.slice(0, 120); f.step = "state"; setPlaceholder("State, e.g. Texas or TX");
      return say("Which state do you sell into? (Want just a radius around your ZIP instead? The " + L("#free", "form on the homepage") + " does that.)", [cancelChip()]);
    }
    if (f.step === "state") {
      var st = findState(text);
      if (!st) return say("I didn't catch the state. Type its name or two-letter code, like Florida or FL.", [cancelChip()]);
      d.state = st; f.step = "cat"; setPlaceholder();
      return say("Got it: " + esc(STATES[st]) + ". Which category?", CATS.map(function (c) { return chip(c[1], function () { pickCat(c[0]); }); }).concat([cancelChip()]));
    }
    if (f.step === "cat") {
      var t = findTopic(text), c = (t && t.cat) || (/every|all|any|everything/.test(norm(text)) ? "all" : "");
      if (!c) { var m = CATS.filter(function (x) { return norm(x[1]).indexOf(norm(text).trim()) >= 0; })[0]; c = m ? m[0] : ""; }
      if (!c) return say("Pick one of these:", CATS.map(function (x) { return chip(x[1], function () { pickCat(x[0]); }); }).concat([cancelChip()]));
      return pickCat(c);
    }
    if (f.step === "spec") {
      var nn = norm(text);
      var g = SPECS.filter(function (s) { return (d.cat === "all" || s[2] === d.cat) && norm(s[1]).indexOf(nn.trim()) >= 0; })[0];
      if (!g && /every|all|any|no|none|skip/.test(nn)) return pickSpec("");
      if (!g) return say("I didn't find that specialty. Pick one, or every specialty:", specChips());
      return pickSpec(g[0]);
    }
    if (f.step === "confirm") {
      if (/ (yes|yep|yeah|sure|ok|okay|go|send|do it|correct|right) /.test(norm(text))) return trialSend();
      return say("Want me to send it?", confirmChips());
    }
  }
  function pickCat(c) {
    var f = flow; if (!f || f.type !== "trial") return;
    f.d.cat = c; f.step = "spec";
    if (c === "all") return pickSpec("");
    return say("Only one specialty, or every specialty in " + (c === "all" ? "the state" : esc(CATS.filter(function (x) { return x[0] === c; })[0][1].toLowerCase())) + "?", specChips());
  }
  function specChips() {
    var d = flow.d, list = SPECS.filter(function (s) { return d.cat === "all" ? false : s[2] === d.cat; });
    return [chip("Every specialty", function () { pickSpec(""); })].concat(list.map(function (s) { return chip(s[1], function () { pickSpec(s[0]); }); })).concat([cancelChip()]);
  }
  function pickSpec(k) {
    var f = flow; if (!f || f.type !== "trial") return;
    f.d.spec = k; f.step = "confirm"; setPlaceholder();
    var d = f.d, cat = CATS.filter(function (x) { return x[0] === d.cat; })[0][1], sp = SPECS.filter(function (s) { return s[0] === k; })[0];
    return say("Here's what I'll set up:<br><b>" + esc(STATES[d.state]) + "</b> · " + esc(cat) + (sp ? " · " + esc(sp[1]) : "") +
      "<br>to <b>" + esc(d.email) + "</b> (" + esc(d.company) + ")<br>Your first list arrives within minutes. Send it?", confirmChips());
  }
  function confirmChips() { return [chip("Yes, send my first list", trialSend), chip("Start over", startTrial, true), cancelChip()]; }
  function source() {
    var ref = "";
    try { var r = document.referrer ? new URL(document.referrer) : null;
      ref = !r ? "" : (r.hostname.replace(/^www\./, "") === location.hostname.replace(/^www\./, "") ? r.pathname : r.hostname.replace(/^www\./, "")); } catch (e) {}
    return ["chat", ref, location.pathname].join("|").slice(0, 40);
  }
  function post(path, body) {
    var ctrl = window.AbortController ? new AbortController() : null, timer = ctrl && setTimeout(function () { ctrl.abort(); }, 12000);
    return fetch(W + path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), signal: ctrl && ctrl.signal})
      .then(function (r) { clearTimeout(timer); return r.json().catch(function () { return {ok: false, status: r.status}; }).then(function (j) { j.status = r.status; return j; }); });
  }
  function trialSend() {
    var f = flow; if (!f || f.type !== "trial" || busy) return;
    var d = f.d; busy = true;
    var body = {email: d.email, company: d.company, state: d.state, category: d.cat, specialties: d.spec || "", website: "", src: source()};
    return post("/signup", body).then(function (j) {
      busy = false;
      if (!j.ok) return say(esc(j.error || "Something was missing.") + " Want to try again?", [chip("Start over", startTrial), cancelChip()]);
      flow = null; setPlaceholder();
      var where = esc(STATES[d.state]);
      return say((j.note ? "You're already signed up, so nothing new to do: " : "<b>You're in.</b> ") + "Your first free list (" + where +
        ") is on its way to <b>" + esc(d.email) + "</b> and arrives within minutes; the second comes with next week's federal file. " +
        "It's from matt@panelready.co: if you don't see it, check spam.", [chip("What's in a list?", function () { answer(BY.inlist); }), chip("Pricing", function () { answer(BY.pricing); })]);
    }).catch(function () {
      busy = false; flow = null; setPlaceholder();
      var m = "mailto:" + MAIL + "?subject=" + encodeURIComponent("Two free lists") + "&body=" + encodeURIComponent("Please send me the next two lists.\nState: " +
        STATES[d.state] + "\nCategory: " + d.cat + (d.spec ? "\nSpecialty: " + d.spec : "") + "\nCompany: " + d.company + "\nEmail: " + d.email);
      return say("That didn't go through on my end. <a href=\"" + m + "\">Send it by email instead</a> and Matt will set it up by hand.");
    });
  }

  // account link: the same request as the account page; the answer never says whether the address has an account
  function startLink() {
    flow = {type: "link"}; setPlaceholder("The email your lists go to");
    return say("What's the email address your lists go to? If it has a subscription, I'll email it a private sign-in link.", [cancelChip()]);
  }
  function linkStep(f, text, honey) {
    if (!EMAIL.test(text)) return say("That doesn't look like an email address. Which address do your lists go to?", [cancelChip()]);
    busy = true;
    return post("/link", {email: text.toLowerCase(), website: honey || ""}).then(function (j) {
      busy = false; flow = null; setPlaceholder();
      if (!j.ok) return say(esc(j.error || "That didn't go through.") + " You can also use the " + L("account/", "account page") + ".", MENU());
      return say("Done. If <b>" + esc(text.toLowerCase()) + "</b> has a PanelReady subscription, a sign-in link is on its way (within the hour). " +
        "On the free trial? Your lists come by email; the account page opens once you subscribe.", [chip("Pricing", function () { answer(BY.pricing); }), chip("Ask Matt a question", function () { startAsk(""); }, true)]);
    }).catch(function () { busy = false; flow = null; setPlaceholder(); return say("I couldn't reach the server. Try the " + L("account/", "account page") + ", or email " + MAIL + "."); });
  }

  // a question for Matt: the question, their email, then POST /ask (or a ready-made email if that fails)
  function startAsk(q) {
    flow = {type: "ask", d: {question: q || ""}, step: q ? "email" : "question"};
    setPlaceholder(q ? "you@yourcompany.com" : "Your question for Matt");
    return say(q ? "Sure. What email should Matt reply to?" : "Sure: what would you like to ask Matt? Type it in your own words.", [cancelChip()]);
  }
  function askStep(f, text, honey) {
    if (f.step === "question") {
      f.d.question = text; f.step = "email"; setPlaceholder("you@yourcompany.com");
      return say("Thanks. What email should Matt reply to?", [cancelChip()]);
    }
    if (f.step === "email") {
      if (!EMAIL.test(text)) return say("That doesn't look like an email address. Where should Matt reply?", [cancelChip()]);
      f.d.email = text.toLowerCase(); busy = true;
      return post("/ask", {email: f.d.email, question: f.d.question, page: location.pathname, website: honey || ""}).then(function (j) {
        busy = false;
        if (j.ok) { flow = null; setPlaceholder();
          return say("<b>Sent.</b> Matt will reply to " + esc(f.d.email) + " by email. Anything else I can help with?", MENU().slice(0, 4)); }
        if (j.status && j.status < 500 && j.error) return say(esc(j.error), [cancelChip()]);
        return mailFallback(f.d);
      }).catch(function () { busy = false; return mailFallback(f.d); });
    }
  }
  function mailFallback(d) {
    flow = null; setPlaceholder();
    var m = "mailto:" + MAIL + "?subject=" + encodeURIComponent("Question from the website") + "&body=" + encodeURIComponent(d.question + "\n\n(Reply to: " + d.email + ")");
    return say("I couldn't send that from here. <a href=\"" + m + "\">Email it to Matt</a> instead (your question is already filled in).");
  }

  // "do you have home health agencies in Florida?": yes, where they are, and what to do next
  function coverage(t, st) {
    var catName = (CATS.filter(function (c) { return c[0] === t.cat; })[0] || [0, ""])[1];
    var spec = SPECS.filter(function (s) { return s[0] === t.key; })[0];
    var html = "Yes: new " + esc(t.name) + (st ? " in " + esc(STATES[st]) : "") + " are on the lists every week" +
      (catName ? ", in " + esc(catName) : "") + "." + (spec ? " You can also pick <b>" + esc(spec[1]) + "</b> as your specialty so your list carries only those, in one state, or in every state on the one-specialty plan." : "");
    return say(html, [chip(st ? "How many in " + STATES[st] + "?" : "How many this week?", function () { counts(st, t, !st); }),
      chip("Start my free trial", startTrial), chip("Pricing", function () { answer(BY.pricing); }, true)]);
  }

  // live counts: the public numbers behind panelready.co/search/ (no names or contacts)
  var IX = null;
  function index() {
    if (IX) return Promise.resolve(IX);
    return fetch(W + "/search?f=index").then(function (r) { if (!r.ok) throw new Error("no counts"); return r.json(); }).then(function (j) { IX = j; return j; });
  }
  function startCounts(text) {
    flow = {type: "counts", step: "state", d: {}}; setPlaceholder("A state, or \"all\"");
    return say("Which state? (Or \"all\" for the whole country.)", [chip("Whole country", function () { flow.d.all = true; askWhat(); })].concat([cancelChip()]));
  }
  function askWhat() {
    flow.step = "what"; setPlaceholder("A specialty or category, or \"all\"");
    return say("Which specialty or category? For example ABA, physical therapy, home health, FQHCs, dental, or \"all\".",
      [chip("All practices", function () { var d = flow.d; flow = null; setPlaceholder(); counts(d.state || "", null, !d.state); })].concat([cancelChip()]));
  }
  function countsStep(f, text) {
    if (f.step === "state") {
      var whole = / (all|whole|every|country|nationwide|us|usa) /.test(norm(text)), st = whole ? "" : findState(text);
      if (!whole && !st) return say("I didn't catch the state. Type its name or two-letter code, or \"all\".", [cancelChip()]);
      if (f.d.topic) { flow = null; setPlaceholder(); return counts(st, f.d.topic, whole); }
      if (whole) f.d.all = true; else f.d.state = st;
      return askWhat();
    }
    if (f.step === "what") {
      var d = f.d; flow = null; setPlaceholder();
      var t = / (all|everything|every|any) /.test(norm(text)) ? null : findTopic(text);
      if (!t && !/ (all|everything|every|any) /.test(norm(text))) return say("I don't have numbers by that name. Try a specialty like ABA, counselors, PT, home health, DME or FQHCs, or \"all\".", [chip("All practices", function () { counts(d.state || "", null, !d.state); }), chip("Try again", function () { flow = {type: "counts", step: "what", d: d}; askWhat(); }, true)]);
      return counts(d.state || "", t, !d.state);
    }
  }
  function counts(st, topic, whole) {
    flow = null; setPlaceholder();
    if (!st && !whole) { flow = {type: "counts", step: "state", d: {topic: topic}}; setPlaceholder("A state, or \"all\"");
      return say("Which state? (Or \"all\" for the whole country.)", [chip("Whole country", function () { flow.d.all = true; flow.step = "what"; counts("", topic, true); }), cancelChip()]); }
    return index().then(function (ix) {
      var sti = st ? ix.states.indexOf(st) : -1, last = ix.weeks.length - 1, wk = 0, org = 0, four = 0;
      if (st && sti < 0) return say("I don't have numbers for " + esc(STATES[st] || st) + " yet.");
      ix.r.forEach(function (x) {
        if (x[0] !== 0 || (st && x[2] !== sti)) return;
        var sp = ix.specs[x[3]];
        if (topic && topic.rx && !topic.rx.test(sp[0])) return;
        if (topic && !topic.rx && topic.cat && ix.cats[sp[1]] !== topic.cat) return;
        if (x[1] === last) { wk += x[5]; if (x[4] === 0) org += x[5]; }
        if (x[1] > last - 4) four += x[5];
      });
      var what = topic ? topic.name : "practices", where = st ? STATES[st] : "the whole country";
      var d = new Date(ix.weeks[last] + "T12:00:00"), when = d.toLocaleDateString("en-US", {month: "long", day: "numeric"});
      var html = "New " + esc(what) + " in " + esc(where) + ", week ending " + esc(when) + ":<span class=\"prc-big\">" + wk.toLocaleString("en-US") + "</span>" +
        (wk ? plural(org, "organization") + ", " + plural(wk - org, "sole proprietor") + ". " : "") +
        "The last 4 weeks: <b>" + four.toLocaleString("en-US") + "</b>. Break it down by county, city or ZIP on the " + L("search/", "live search") + ".";
      return say(html, [chip("Start my free trial", startTrial), chip("Look up another", function () { startCounts(""); }), chip("Pricing", function () { answer(BY.pricing); }, true)]);
    }).catch(function () { return say("The counts are being refreshed right now. Try the " + L("search/", "live search page") + " in a few minutes."); });
  }

  // ------------------------------------------------------------------ go
  function boot() { build(); if (/[?&]help(=|&|$)/.test(location.search) || location.hash === "#help") open(true); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
  window.PanelReadyChat = {open: function () { open(true); }, _kb: KB, _route: route, _findState: findState, _findTopic: findTopic, _best: best};
})();
