/* AMOR HOSTING - i18n (EN / AR / FR / ES) + 3D language picker */
(function(){
if(window.__amorI18n)return;window.__amorI18n=1;
var L={en:{n:'English',f:'🇬🇧',i:-1},ar:{n:'العربية',f:'🇪🇬',i:0},fr:{n:'Français',f:'🇫🇷',i:1},es:{n:'Español',f:'🇪🇸',i:2}};
var D={
'VPS sign up':['تسجيل VPS','Inscription VPS','Registro VPS'],'Reinstall':['إعادة تثبيت','Réinstaller','Reinstalar'],'Create VPS account':['إنشاء حساب VPS','Créer un compte VPS','Crear cuenta VPS'],
'One account to order, manage and renew your servers.':['حساب واحد لطلب وإدارة وتجديد خوادمك.','Un seul compte pour commander, gérer et renouveler vos serveurs.','Una cuenta para pedir, gestionar y renovar tus servidores.'],
'Username (optional)':['اسم المستخدم (اختياري)','Identifiant (facultatif)','Usuario (opcional)'],'Password (min 6 characters)':['كلمة المرور (6 أحرف على الأقل)','Mot de passe (6 caractères min.)','Contraseña (mín. 6 caracteres)'],
'Create your VPS account':['أنشئ حساب VPS','Créez votre compte VPS','Crea tu cuenta VPS'],
'Features':['المميزات','Fonctionnalités','Características'],'How it works':['كيف يعمل','Comment ça marche','Cómo funciona'],'VPS':['VPS','VPS','VPS'],
'My VPS':['خوادمي','Mes VPS','Mis VPS'],'Dashboard':['لوحة التحكم','Tableau de bord','Panel'],'Logout':['خروج','Déconnexion','Salir'],'Login':['دخول','Connexion','Entrar'],
'Get started':['ابدأ الآن','Commencer','Empezar'],'All systems operational':['كل الأنظمة تعمل','Tous les systèmes fonctionnent','Todos los sistemas operativos'],
'Upload any website or project with all its files. AMOR detects the main file, installs what it needs and launches it automatically. Need more power? Grab your own VPS.':['ارفع أي موقع أو مشروع بكل ملفاته. يكتشف AMOR الملف الرئيسي ويثبّت المتطلبات ويشغّله تلقائياً. محتاج قوة أكبر؟ احصل على VPS خاص بك.','Téléversez n’importe quel site ou projet avec tous ses fichiers. AMOR détecte le fichier principal, installe les dépendances et le lance automatiquement. Besoin de plus de puissance ? Prenez votre propre VPS.','Sube cualquier sitio o proyecto con todos sus archivos. AMOR detecta el archivo principal, instala lo necesario y lo ejecuta automáticamente. ¿Necesitas más potencia? Consigue tu propio VPS.'],
'Start hosting free':['ابدأ الاستضافة مجاناً','Héberger gratuitement','Empieza gratis'],'Explore VPS':['استكشف VPS','Découvrir les VPS','Explorar VPS'],
'Uptime':['وقت التشغيل','Disponibilité','Disponibilidad'],'Deploy time':['وقت النشر','Temps de déploiement','Tiempo de despliegue'],'Upload limit':['حد الرفع','Limite d’envoi','Límite de subida'],
'Auto-detect & auto-run':['اكتشاف وتشغيل تلقائي','Détection et lancement auto','Detección y ejecución automática'],
'Drop a folder or ZIP. We find the entry file (index.html, main.py, app.py, server.js, package.json…) and start it for you.':['ارفع مجلداً أو ملف ZIP. نكتشف الملف الرئيسي (index.html و main.py و app.py و server.js و package.json…) ونشغّله لك.','Déposez un dossier ou un ZIP. Nous trouvons le fichier d’entrée (index.html, main.py, app.py, server.js, package.json…) et le lançons pour vous.','Suelta una carpeta o ZIP. Encontramos el archivo de entrada (index.html, main.py, app.py, server.js, package.json…) y lo iniciamos por ti.'],
'Every language':['كل لغات البرمجة','Tous les langages','Todos los lenguajes'],
'Static sites, Python, Node.js, PHP and shell projects. Dependencies are installed automatically.':['مواقع ثابتة وبايثون و Node.js و PHP ومشاريع shell. تُثبَّت المكتبات تلقائياً.','Sites statiques, Python, Node.js, PHP et scripts shell. Les dépendances sont installées automatiquement.','Sitios estáticos, Python, Node.js, PHP y scripts shell. Las dependencias se instalan automáticamente.'],
'Live URL instantly':['رابط مباشر فوراً','URL en direct instantanément','URL en vivo al instante'],
'Every project gets its own public link the second it is uploaded. Share it right away.':['كل مشروع يحصل على رابط عام خاص به لحظة رفعه. شاركه فوراً.','Chaque projet obtient son lien public dès l’envoi. Partagez-le tout de suite.','Cada proyecto recibe su enlace público en cuanto se sube. Compártelo al instante.'],
'Live console':['وحدة تحكم مباشرة','Console en direct','Consola en vivo'],
'Real-time logs, start / stop / restart and a built-in file manager with editor.':['سجلات لحظية وتشغيل / إيقاف / إعادة تشغيل ومدير ملفات مع محرر مدمج.','Journaux en temps réel, démarrage / arrêt / redémarrage et gestionnaire de fichiers avec éditeur.','Registros en tiempo real, iniciar / detener / reiniciar y gestor de archivos con editor.'],
'Isolated & protected':['معزول ومحمي','Isolé et protégé','Aislado y protegido'],
'CPU limits, private source files and rate limiting keep every project safe.':['حدود المعالج وحماية ملفات المصدر وتحديد المعدل تحافظ على أمان كل مشروع.','Limites CPU, fichiers sources privés et limitation de débit protègent chaque projet.','Límites de CPU, archivos fuente privados y limitación de tasa protegen cada proyecto.'],
'Dedicated VPS':['VPS مخصص','VPS dédié','VPS dedicado'],
'Full root access, NVMe storage and your choice of OS. Order in under a minute.':['صلاحيات root كاملة وتخزين NVMe واختيار النظام. اطلب في أقل من دقيقة.','Accès root complet, stockage NVMe et choix de l’OS. Commandez en moins d’une minute.','Acceso root completo, almacenamiento NVMe y elección de SO. Pide en menos de un minuto.'],
'Create account':['إنشاء حساب','Créer un compte','Crear cuenta'],'Sign up with phone, email or Google. Your server is created for you.':['سجّل بالهاتف أو البريد أو جوجل. يتم تجهيز سيرفرك تلقائياً.','Inscrivez-vous par téléphone, e-mail ou Google. Votre serveur est créé pour vous.','Regístrate con teléfono, correo o Google. Tu servidor se crea por ti.'],
'Drop your files':['ارفع ملفاتك','Déposez vos fichiers','Sube tus archivos'],'Upload a whole folder or a ZIP. Nothing to configure.':['ارفع مجلداً كاملاً أو ZIP. لا توجد إعدادات.','Envoyez un dossier entier ou un ZIP. Rien à configurer.','Sube una carpeta entera o un ZIP. Nada que configurar.'],
'Go live':['انشر الآن','Mettez en ligne','Publica'],'The main file is detected and started automatically. Copy your link.':['يُكتشف الملف الرئيسي ويُشغَّل تلقائياً. انسخ رابطك.','Le fichier principal est détecté et lancé automatiquement. Copiez votre lien.','El archivo principal se detecta y se inicia automáticamente. Copia tu enlace.'],
'Pick a plan and register your VPS request in under a minute.':['اختر باقة وسجّل طلب VPS في أقل من دقيقة.','Choisissez une offre et enregistrez votre VPS en moins d’une minute.','Elige un plan y registra tu VPS en menos de un minuto.'],
'MOST POPULAR':['الأكثر طلباً','LE PLUS POPULAIRE','MÁS POPULAR'],' / month':[' / شهر',' / mois',' / mes'],
'Create your account and have your project online before your coffee cools.':['أنشئ حسابك وشغّل مشروعك قبل أن تبرد قهوتك.','Créez votre compte et mettez votre projet en ligne avant que votre café refroidisse.','Crea tu cuenta y pon tu proyecto en línea antes de que se enfríe tu café.'],
'Create free account':['أنشئ حساباً مجانياً','Créer un compte gratuit','Crear cuenta gratis'],'© 2026 AMOR HOSTING · Built for builders':['© 2026 AMOR HOSTING · صُمم للمطوّرين','© 2026 AMOR HOSTING · Conçu pour les créateurs','© 2026 AMOR HOSTING · Hecho para creadores'],
'Sign in to your hosting dashboard.':['سجّل دخولك إلى لوحة الاستضافة.','Connectez-vous à votre tableau de bord.','Inicia sesión en tu panel de hosting.'],
'Username / Email / Phone':['اسم المستخدم / البريد / الهاتف','Identifiant / E-mail / Téléphone','Usuario / Correo / Teléfono'],'Password':['كلمة المرور','Mot de passe','Contraseña'],
'your username':['اسم المستخدم','votre identifiant','tu usuario'],'Sign in':['تسجيل الدخول','Se connecter','Iniciar sesión'],'OR':['أو','OU','O'],
'Continue with Google':['المتابعة بجوجل','Continuer avec Google','Continuar con Google'],'Continue with Discord':['المتابعة بديسكورد','Continuer avec Discord','Continuar con Discord'],
'NEW HERE?':['جديد هنا؟','NOUVEAU ICI ?','¿NUEVO AQUÍ?'],'HAVE AN ACCOUNT?':['عندك حساب؟','DÉJÀ UN COMPTE ?','¿YA TIENES CUENTA?'],
'Your hosting server is ready the moment you join.':['سيرفر الاستضافة جاهز لحظة انضمامك.','Votre serveur est prêt dès votre inscription.','Tu servidor está listo en cuanto te unes.'],
'Phone number':['رقم الهاتف','Numéro de téléphone','Número de teléfono'],'Email':['البريد','E-mail','Correo'],'Send verification code':['إرسال رمز التحقق','Envoyer le code de vérification','Enviar código de verificación'],
'Username (optional)':['اسم المستخدم (اختياري)','Identifiant (facultatif)','Usuario (opcional)'],'Password (min 4 characters)':['كلمة المرور (4 أحرف على الأقل)','Mot de passe (4 caractères min.)','Contraseña (mín. 4 caracteres)'],
'Email address':['البريد الإلكتروني','Adresse e-mail','Correo electrónico'],
'Enter your phone number':['أدخل رقم هاتفك','Entrez votre numéro','Introduce tu teléfono'],'Enter your phone and the code':['أدخل الهاتف والرمز','Entrez le téléphone et le code','Introduce el teléfono y el código'],
'Password must be at least 4 characters':['كلمة المرور 4 أحرف على الأقل','Le mot de passe doit faire 4 caractères min.','La contraseña debe tener al menos 4 caracteres'],
'Account created ✔':['تم إنشاء الحساب ✔','Compte créé ✔','Cuenta creada ✔'],'Could not reach the server':['تعذر الاتصال بالسيرفر','Serveur injoignable','No se pudo conectar con el servidor'],
'VPS Registration':['تسجيل VPS','Commande VPS','Registro de VPS'],'Choose a plan, system and location, then register. Your server is activated after review.':['اختر الباقة والنظام والموقع ثم سجّل. يتم تفعيل سيرفرك بعد المراجعة.','Choisissez une offre, un système et un lieu puis validez. Votre serveur est activé après vérification.','Elige plan, sistema y ubicación y regístrate. Tu servidor se activa tras la revisión.'],
'1 · PLAN':['١ · الباقة','1 · OFFRE','1 · PLAN'],'2 · OPERATING SYSTEM':['٢ · نظام التشغيل','2 · SYSTÈME','2 · SISTEMA OPERATIVO'],'3 · LOCATION':['٣ · الموقع','3 · EMPLACEMENT','3 · UBICACIÓN'],'4 · YOUR DETAILS':['٤ · بياناتك','4 · VOS INFORMATIONS','4 · TUS DATOS'],
'Full name':['الاسم الكامل','Nom complet','Nombre completo'],'Phone / WhatsApp / Telegram username':['هاتف / واتساب / يوزر تليجرام','Téléphone / WhatsApp / Telegram','Teléfono / WhatsApp / Telegram'],'Notes (optional)':['ملاحظات (اختياري)','Notes (facultatif)','Notas (opcional)'],
'Billing: monthly':['الدفع: شهرياً','Facturation : mensuelle','Facturación: mensual'],'Billing: every 3 months (save 5%)':['الدفع: كل 3 شهور (وفّر 5%)','Facturation : trimestrielle (-5 %)','Facturación: trimestral (ahorra 5 %)'],'Billing: yearly (save 15%)':['الدفع: سنوياً (وفّر 15%)','Facturation : annuelle (-15 %)','Facturación: anual (ahorra 15 %)'],
'ORDER SUMMARY':['ملخص الطلب','RÉCAPITULATIF','RESUMEN DEL PEDIDO'],'Plan':['الباقة','Offre','Plan'],'System':['النظام','Système','Sistema'],'Location':['الموقع','Lieu','Ubicación'],'Billing':['الدفع','Facturation','Facturación'],'Monthly':['شهرياً','Mensuel','Mensual'],
'Register VPS':['سجّل VPS','Commander le VPS','Registrar VPS'],'No payment is taken online. Your request is sent to our team and you will be contacted to finish activation.':['لا يتم أي دفع أونلاين. يصل طلبك لفريقنا وسنتواصل معك لإتمام التفعيل.','Aucun paiement en ligne. Votre demande est transmise à notre équipe qui vous contactera pour l’activation.','No se cobra nada en línea. Tu solicitud llega a nuestro equipo y te contactaremos para activarlo.'],
'YOUR VPS REQUESTS':['طلبات VPS الخاصة بك','VOS DEMANDES VPS','TUS SOLICITUDES VPS'],'Please choose a plan, an operating system and a location.':['اختر الباقة ونظام التشغيل والموقع.','Choisissez une offre, un système et un emplacement.','Elige un plan, un sistema operativo y una ubicación.'],
'Please fill in your name, email and contact.':['أدخل الاسم والبريد وطريقة التواصل.','Renseignez nom, e-mail et contact.','Completa nombre, correo y contacto.'],'Please sign in to order a VPS.':['سجّل دخولك لطلب VPS.','Connectez-vous pour commander un VPS.','Inicia sesión para pedir un VPS.'],
'Something went wrong.':['حدث خطأ ما.','Une erreur est survenue.','Algo salió mal.'],
'My servers':['خوادمي','Mes serveurs','Mis servidores'],'Order new VPS':['اطلب VPS جديد','Commander un VPS','Pedir nuevo VPS'],'No VPS yet':['لا يوجد VPS بعد','Aucun VPS pour l’instant','Aún no hay VPS'],
'Order your first server and it will appear here.':['اطلب أول سيرفر وسيظهر هنا.','Commandez votre premier serveur, il apparaîtra ici.','Pide tu primer servidor y aparecerá aquí.'],
'Status':['الحالة','Statut','Estado'],'Pending':['قيد المراجعة','En attente','Pendiente'],'Active':['نشط','Actif','Activo'],'Suspended':['موقوف','Suspendu','Suspendido'],'Cancelled':['ملغي','Annulé','Cancelado'],
'IP address':['عنوان IP','Adresse IP','Dirección IP'],'Hostname':['اسم المضيف','Nom d’hôte','Nombre de host'],'Username':['المستخدم','Utilisateur','Usuario'],'Expires':['ينتهي','Expire','Vence'],
'Start':['تشغيل','Démarrer','Iniciar'],'Stop':['إيقاف','Arrêter','Detener'],'Reboot':['إعادة تشغيل','Redémarrer','Reiniciar'],'Cancel':['إلغاء','Annuler','Cancelar'],
'Waiting for activation. You will see your IP and login here once it is ready.':['في انتظار التفعيل. ستظهر هنا بيانات IP والدخول عندما يجهز السيرفر.','En attente d’activation. Votre IP et vos accès apparaîtront ici.','Esperando activación. Aquí verás tu IP y acceso cuando esté listo.'],
'Connect with SSH':['الاتصال عبر SSH','Connexion SSH','Conectar por SSH'],'Copy':['نسخ','Copier','Copiar'],'Copied':['تم النسخ','Copié','Copiado'],'Power':['الطاقة','Alimentation','Energía'],'Online':['يعمل','En ligne','En línea'],'Offline':['متوقف','Hors ligne','Sin conexión'],
'Do you really want to cancel this VPS?':['متأكد إنك عايز تلغي الـ VPS ده؟','Voulez-vous vraiment annuler ce VPS ?','¿Seguro que quieres cancelar este VPS?'],
'Assist':['المساعد','Assistant','Asistente'],'Ask about hosting, deployments or VPS…':['اسأل عن الاستضافة أو النشر أو VPS…','Posez une question sur l’hébergement, le déploiement ou les VPS…','Pregunta sobre hosting, despliegues o VPS…'],
'Send':['إرسال','Envoyer','Enviar'],'Sign in to chat with Assist.':['سجّل دخولك للتحدث مع المساعد.','Connectez-vous pour discuter avec l’assistant.','Inicia sesión para chatear con el asistente.'],
'Hi! I can help with deployments, errors and choosing a VPS plan.':['أهلاً! أقدر أساعدك في النشر والأخطاء واختيار باقة VPS.','Bonjour ! Je peux vous aider pour les déploiements, les erreurs et le choix d’un VPS.','¡Hola! Puedo ayudarte con despliegues, errores y a elegir un plan VPS.'],
'Incorrect login details. Use your username, email or phone together with your password.':['بيانات الدخول غير صحيحة. استخدم اسم المستخدم أو البريد أو الهاتف مع كلمة المرور.','Identifiants incorrects. Utilisez votre identifiant, e-mail ou téléphone avec votre mot de passe.','Datos incorrectos. Usa tu usuario, correo o teléfono junto con la contraseña.'],
'Too many attempts. Please wait a moment.':['محاولات كثيرة. انتظر قليلاً.','Trop de tentatives. Patientez un instant.','Demasiados intentos. Espera un momento.']
};
var H={
hero_title:{en:'Deploy <span class="grad">anything.</span><br>Instantly.',ar:'انشر <span class="grad">أي شيء.</span><br>فوراً.',fr:'Déployez <span class="grad">tout.</span><br>Instantanément.',es:'Despliega <span class="grad">lo que sea.</span><br>Al instante.'},
feat_title:{en:'Everything a host should be.<br><span class="grad">Nothing it shouldn\'t.</span>',ar:'كل ما يجب أن تكونه الاستضافة.<br><span class="grad">وبدون أي زيادات.</span>',fr:'Tout ce qu’un hébergeur doit être.<br><span class="grad">Rien de superflu.</span>',es:'Todo lo que un hosting debe ser.<br><span class="grad">Nada que sobre.</span>'},
how_title:{en:'Three steps to <span class="grad">live.</span>',ar:'ثلاث خطوات حتى <span class="grad">تنشر.</span>',fr:'Trois étapes pour être <span class="grad">en ligne.</span>',es:'Tres pasos para estar <span class="grad">en vivo.</span>'},
vps_title:{en:'Your own server. <span class="grad">Full root.</span>',ar:'سيرفرك الخاص. <span class="grad">صلاحيات root كاملة.</span>',fr:'Votre propre serveur. <span class="grad">Root complet.</span>',es:'Tu propio servidor. <span class="grad">Root completo.</span>'},
cta_title:{en:'Ready to <span class="grad">launch?</span>',ar:'جاهز <span class="grad">تنطلق؟</span>',fr:'Prêt à <span class="grad">décoller ?</span>',es:'¿Listo para <span class="grad">despegar?</span>'},
login_title:{en:'Welcome <span class="grad">back</span>',ar:'أهلاً <span class="grad">بعودتك</span>',fr:'Bon <span class="grad">retour</span>',es:'Bienvenido <span class="grad">de nuevo</span>'},
reg_title:{en:'Create your <span class="grad">account</span>',ar:'أنشئ <span class="grad">حسابك</span>',fr:'Créez votre <span class="grad">compte</span>',es:'Crea tu <span class="grad">cuenta</span>'},
reg_steps:{en:'1) Open <a href="https://t.me/AmorffBOT" target="_blank" style="color:var(--c);font-weight:700">@AmorffBOT</a> and press <b>/start</b><br>2) Send <code class="mono" style="color:var(--g)">/bind 01xxxxxxxxx</code><br>3) Enter the same number below. Your code arrives in the bot.',ar:'١) افتح <a href="https://t.me/AmorffBOT" target="_blank" style="color:var(--c);font-weight:700">@AmorffBOT</a> واضغط <b>/start</b><br>٢) أرسل <code class="mono" style="color:var(--g)">/bind 01xxxxxxxxx</code><br>٣) اكتب نفس الرقم هنا. يصلك الرمز داخل البوت.',fr:'1) Ouvrez <a href="https://t.me/AmorffBOT" target="_blank" style="color:var(--c);font-weight:700">@AmorffBOT</a> et appuyez sur <b>/start</b><br>2) Envoyez <code class="mono" style="color:var(--g)">/bind 01xxxxxxxxx</code><br>3) Saisissez le même numéro ci-dessous. Le code arrive dans le bot.',es:'1) Abre <a href="https://t.me/AmorffBOT" target="_blank" style="color:var(--c);font-weight:700">@AmorffBOT</a> y pulsa <b>/start</b><br>2) Envía <code class="mono" style="color:var(--g)">/bind 01xxxxxxxxx</code><br>3) Escribe el mismo número abajo. El código llega al bot.'},
order_title:{en:'Order your <span class="grad">VPS</span>',ar:'اطلب <span class="grad">VPS</span> الخاص بك',fr:'Commandez votre <span class="grad">VPS</span>',es:'Pide tu <span class="grad">VPS</span>'},
panel_title:{en:'My <span class="grad">servers</span>',ar:'<span class="grad">خوادمي</span>',fr:'Mes <span class="grad">serveurs</span>',es:'Mis <span class="grad">servidores</span>'}
};
var PAT=[[/^Choose (.+)$/,['اختر $1','Choisir $1','Elegir $1']],[/^(.+) bandwidth$/,['نقل بيانات $1','$1 de bande passante','$1 de ancho de banda']],[/^Expires (.+)$/,['ينتهي $1','Expire le $1','Vence el $1']]];
var cur='en';
function tr(s){
  if(cur==='en') return s; var k=s.trim(); if(!k) return s; var i=L[cur].i, v=D[k];
  if(v&&v[i]) return s.replace(k,v[i]);
  for(var p=0;p<PAT.length;p++){var m=k.match(PAT[p][0]); if(m) return s.replace(k,PAT[p][1][i].replace(/\$(\d)/g,function(_,n){return m[n]}));}
  return s;
}
window.t=function(s){return tr(s)}; window.AMOR_LANG=function(){return cur};
var SKIP={SCRIPT:1,STYLE:1,TEXTAREA:1,CODE:1,PRE:1,NOSCRIPT:1};
function walk(root){
  var w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:function(n){var p=n.parentNode;if(!p||SKIP[p.nodeName]||(p.closest&&p.closest('[data-i18n],[data-noi18n],#scene')))return NodeFilter.FILTER_REJECT;return n.nodeValue.trim()?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT;}});
  var n,list=[];while((n=w.nextNode()))list.push(n);
  list.forEach(function(n){if(n._o===undefined)n._o=n.nodeValue;var out=tr(n._o);if(n.nodeValue!==out)n.nodeValue=out;});
  if(root.querySelectorAll)root.querySelectorAll('[placeholder],[title],option').forEach(function(e){
    ['placeholder','title'].forEach(function(a){if(e.hasAttribute&&e.hasAttribute(a)){if(!e['_o_'+a])e['_o_'+a]=e.getAttribute(a);e.setAttribute(a,tr(e['_o_'+a]));}});});
}
function apply(){
  document.querySelectorAll('[data-i18n]').forEach(function(e){var h=H[e.getAttribute('data-i18n')];if(h)e.innerHTML=h[cur]||h.en;});
  walk(document.body);
  var rtl=cur==='ar';document.documentElement.lang=cur;document.documentElement.dir=rtl?'rtl':'ltr';
  var lb=document.querySelector('.lp-code');if(lb)lb.textContent=cur.toUpperCase();
  document.querySelectorAll('.lp-card').forEach(function(c){c.classList.toggle('on',c.dataset.l===cur)});
}
function setLang(l){cur=L[l]?l:'en';try{localStorage.setItem('amor_lang',cur)}catch(e){}apply();document.dispatchEvent(new Event('amor:lang'));}
window.AMOR_SETLANG=setLang;
function picker(){
  var host=document.querySelector('.nav .links');if(!host||document.querySelector('.langpick'))return;
  var w=document.createElement('div');w.className='langpick';w.setAttribute('data-noi18n','');
  var cards=Object.keys(L).map(function(k){return '<button type="button" class="lp-card" data-l="'+k+'"><b>'+L[k].f+'</b><span>'+L[k].n+'</span></button>'}).join('');
  w.innerHTML='<button type="button" class="lp-btn" aria-label="Language"><span class="globe"><i></i><i></i><i></i><i></i></span><span class="lp-code">EN</span></button><div class="lp-pop glass">'+cards+'</div>';
  host.insertBefore(w,host.firstChild);
  var pop=w.querySelector('.lp-pop');
  w.querySelector('.lp-btn').addEventListener('click',function(e){e.stopPropagation();pop.classList.toggle('open')});
  pop.addEventListener('click',function(e){var c=e.target.closest('.lp-card');if(c){setLang(c.dataset.l);pop.classList.remove('open');}});
  document.addEventListener('click',function(){pop.classList.remove('open')});
}
document.addEventListener('DOMContentLoaded',function(){
  picker();
  var saved=null;try{saved=localStorage.getItem('amor_lang')}catch(e){}
  if(!saved){var n=(navigator.language||'en').slice(0,2).toLowerCase();saved=L[n]?n:'en';}
  cur=L[saved]?saved:'en';apply();
  if('MutationObserver' in window)new MutationObserver(function(ms){if(cur==='en')return;ms.forEach(function(m){m.addedNodes.forEach(function(n){if(n.nodeType===1)walk(n);else if(n.nodeType===3&&n.nodeValue.trim()){n._o=n.nodeValue;n.nodeValue=tr(n._o);}});});}).observe(document.body,{childList:true,subtree:true});
});
})();
