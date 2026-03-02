import json
import logging
import threading
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from datetime import date, time, datetime, timedelta
from django.conf import settings
from django.db import close_old_connections, transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from .models import (
    TransitAspect,
    NatalProfile,
    SlovakCity,
    MomentReport,
    PLANET_SYMBOLS,
    ASPECT_SYMBOLS,
)
from .forms import (
    RegistrationForm,
    LoginForm,
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
    ResendVerificationForm,
)
from .moment_service import MOMENT_TZ, get_or_generate_moment_report
from .transit_data import TRANSIT_DATA
from .gemini_utils import (
    GeminiLimitExceededError,
    generate_gemini_text,
    get_gemini_model,
    has_gemini_key,
    parse_json_payload,
)
from .engine import (
    calculate_natal_positions,
    calculate_natal_chart,
    calculate_transits,
    get_timezone_for_location,
    PLANET_NAMES_SK,
    ASPECT_NAMES_SK,
)
from .security import (
    derive_user_key_b64,
    get_profile_key_from_session,
    store_profile_key_in_session,
)

logger = logging.getLogger(__name__)
ANALYSIS_STATE_LOCK = threading.Lock()
ANALYSIS_IN_PROGRESS = set()
ANALYSIS_LAST_ERROR = {}
PLANET_ORDER = ['sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune', 'pluto']
ASPECT_ORDER = ['conjunction', 'sextile', 'square', 'trine', 'opposition']
ZODIAC_ORDER = [
    'aries', 'taurus', 'gemini', 'cancer', 'leo', 'virgo',
    'libra', 'scorpio', 'sagittarius', 'capricorn', 'aquarius', 'pisces',
]

ZODIAC_LEXICON = {
    'aries': {
        'name': 'Baran',
        'symbol': '♈',
        'color': '#ff6b8f',
        'date_range': '21.3. – 19.4.',
        'element': 'Oheň',
        'modality': 'Kardinálne',
        'ruler': 'Mars',
        'keywords': ['iniciatíva', 'odvaha', 'priamočiarosť'],
        'theme': 'Archetyp začiatku: energia, ktorá štartuje proces a ide dopredu.',
        'description': (
            'Baran prináša rýchlu reakciu, súťaživosť a potrebu konať hneď. '
            'V psychologickej rovine učí zdravému presadeniu seba a nastavovaniu hraníc.'
        ),
        'challenge': 'Netrpezlivosť, impulzívnosť a začínanie bez dokončenia.',
        'advice': 'Spomaľ pred rozhodnutím a premeň impulz na cieľavedomý krok.',
    },
    'taurus': {
        'name': 'Býk',
        'symbol': '♉',
        'color': '#ff9552',
        'date_range': '20.4. – 20.5.',
        'element': 'Zem',
        'modality': 'Pevné',
        'ruler': 'Venuša',
        'keywords': ['stabilita', 'hodnoty', 'zmyslovosť'],
        'theme': 'Archetyp ukotvenia: budovanie istoty, kvality a dlhodobých hodnôt.',
        'description': (
            'Býk podporuje vytrvalosť, praktickosť a schopnosť držať smer aj pri tlaku. '
            'V astrologickej práci zvýrazňuje tému financií, tela a bezpečia.'
        ),
        'challenge': 'Rigidita, odpor k zmene a lipnutie na komforte.',
        'advice': 'Buduj stabilitu, ale vedome si trénuj flexibilitu v malých krokoch.',
    },
    'gemini': {
        'name': 'Blíženci',
        'symbol': '♊',
        'color': '#ffd166',
        'date_range': '21.5. – 20.6.',
        'element': 'Vzduch',
        'modality': 'Premenlivé',
        'ruler': 'Merkúr',
        'keywords': ['komunikácia', 'zvedavosť', 'prepojenia'],
        'theme': 'Archetyp mysle: prepájanie informácií, otázok a perspektív.',
        'description': (
            'Blíženci prinášajú mentálnu svižnosť, humor a schopnosť rýchlo sa učiť. '
            'Silno pôsobia v témach písania, rozhovorov, obchodu a sociálnych sietí.'
        ),
        'challenge': 'Rozptýlenosť, povrchnosť a informačné preťaženie.',
        'advice': 'Vyber si prioritu dňa a daj informáciám jasnú štruktúru.',
    },
    'cancer': {
        'name': 'Rak',
        'symbol': '♋',
        'color': '#7ed0ff',
        'date_range': '21.6. – 22.7.',
        'element': 'Voda',
        'modality': 'Kardinálne',
        'ruler': 'Mesiac',
        'keywords': ['emócie', 'domov', 'ochrana'],
        'theme': 'Archetyp výživy: citová inteligencia, starostlivosť a bezpečné zázemie.',
        'description': (
            'Rak pracuje s pamäťou, rodinnými väzbami a potrebou patriť. '
            'V horoskope ukazuje, kde sa potrebuješ cítiť prijatý a emocionálne v bezpečí.'
        ),
        'challenge': 'Defenzívnosť, precitlivenosť a návrat k starým ranám.',
        'advice': 'Pomenuj emóciu skôr, než zareaguješ, a komunikuj potreby priamo.',
    },
    'leo': {
        'name': 'Lev',
        'symbol': '♌',
        'color': '#f7cd5d',
        'date_range': '23.7. – 22.8.',
        'element': 'Oheň',
        'modality': 'Pevné',
        'ruler': 'Slnko',
        'keywords': ['tvorivosť', 'srdce', 'sebavyjadrenie'],
        'theme': 'Archetyp žiary: vedomé vystúpenie, radosť a autentický prejav.',
        'description': (
            'Lev posilňuje charizmu, veľkorysosť a potrebu tvoriť niečo osobné. '
            'Astrologicky učí zdravej sebadôvere bez potreby neustáleho potvrdenia zvonku.'
        ),
        'challenge': 'Dramatizácia, ego-zraniteľnosť a potreba uznania za každú cenu.',
        'advice': 'Stavaj sebahodnotu na konzistentných činoch, nie na okamžitom aplauze.',
    },
    'virgo': {
        'name': 'Panna',
        'symbol': '♍',
        'color': '#92e58f',
        'date_range': '23.8. – 22.9.',
        'element': 'Zem',
        'modality': 'Premenlivé',
        'ruler': 'Merkúr',
        'keywords': ['analýza', 'služba', 'zlepšovanie'],
        'theme': 'Archetyp remesla: precíznosť, systém a praktické riešenia.',
        'description': (
            'Panna prináša schopnosť rozlíšiť podstatné od šumu a optimalizovať proces. '
            'V natívnej i tranzitnej práci súvisí so zdravím, rutinou a kvalitou detailu.'
        ),
        'challenge': 'Perfekcionizmus, sebakritika a úzkosť z chýb.',
        'advice': 'Zameraj sa na progres, nie perfekciu, a meraj výsledok realisticky.',
    },
    'libra': {
        'name': 'Váhy',
        'symbol': '♎',
        'color': '#79f0ce',
        'date_range': '23.9. – 22.10.',
        'element': 'Vzduch',
        'modality': 'Kardinálne',
        'ruler': 'Venuša',
        'keywords': ['vzťahy', 'rovnováha', 'diplomacia'],
        'theme': 'Archetyp partnerstva: schopnosť tvoriť férové dohody a harmóniu.',
        'description': (
            'Váhy zvýrazňujú estetiku, spoluprácu a sociálnu inteligenciu. '
            'V horoskope ukazujú, kde sa učíš rovnováhe medzi vlastnými a cudzími potrebami.'
        ),
        'challenge': 'Nerozhodnosť, uhýbanie konfliktu a prílišné prispôsobovanie sa.',
        'advice': 'Rozhoduj sa podľa hodnôt, nie podľa strachu zo straty sympatie.',
    },
    'scorpio': {
        'name': 'Škorpión',
        'symbol': '♏',
        'color': '#58b9ff',
        'date_range': '23.10. – 21.11.',
        'element': 'Voda',
        'modality': 'Pevné',
        'ruler': 'Pluto (tradične Mars)',
        'keywords': ['intenzita', 'hĺbka', 'transformácia'],
        'theme': 'Archetyp premeny: odhaľovanie pravdy a práca s vnútornou silou.',
        'description': (
            'Škorpión ide pod povrch a vníma skryté motívy, mocenské dynamiky a lojalitu. '
            'V astrologii súvisí s regeneráciou, psychológiou, dôverou a hranicami.'
        ),
        'challenge': 'Kontrola, žiarlivosť, extrémy a emocionálne testovanie.',
        'advice': 'Premieň potrebu kontroly na vedomú prácu s dôverou a pravdivosťou.',
    },
    'sagittarius': {
        'name': 'Strelec',
        'symbol': '♐',
        'color': '#8d8aff',
        'date_range': '22.11. – 21.12.',
        'element': 'Oheň',
        'modality': 'Premenlivé',
        'ruler': 'Jupiter',
        'keywords': ['vízia', 'sloboda', 'zmysel'],
        'theme': 'Archetyp hľadania: rozširovanie obzoru cez skúsenosť a poznanie.',
        'description': (
            'Strelec podporuje odvahu myslieť vo veľkom a prepájať život s vyšším významom. '
            'Silný je v témach cestovania, štúdia, filozofie a osobného rastu.'
        ),
        'challenge': 'Prehnané očakávania, netaktnosť a útek od detailu.',
        'advice': 'K veľkej vízii pridaj konkrétny plán a pravidelnú spätnú väzbu.',
    },
    'capricorn': {
        'name': 'Kozorožec',
        'symbol': '♑',
        'color': '#b699ff',
        'date_range': '22.12. – 19.1.',
        'element': 'Zem',
        'modality': 'Kardinálne',
        'ruler': 'Saturn',
        'keywords': ['zodpovednosť', 'štruktúra', 'výsledky'],
        'theme': 'Archetyp staviteľa: disciplína, stratégia a dlhodobý výkon.',
        'description': (
            'Kozorožec ukazuje, kde máš prevziať vedenie, povinnosť a trpezlivú prácu. '
            'V horoskope súvisí s kariérou, autoritou, reputáciou a realistickým plánovaním.'
        ),
        'challenge': 'Tvrdosť na seba, pesimizmus a prepracovanie.',
        'advice': 'Buduj tempo, ktoré je udržateľné, a odmeňuj sa aj za čiastkový progres.',
    },
    'aquarius': {
        'name': 'Vodnár',
        'symbol': '♒',
        'color': '#c58bff',
        'date_range': '20.1. – 18.2.',
        'element': 'Vzduch',
        'modality': 'Pevné',
        'ruler': 'Urán (tradične Saturn)',
        'keywords': ['originalita', 'sloboda', 'systémová zmena'],
        'theme': 'Archetyp inovátora: odstup, nové koncepty a budúca perspektíva.',
        'description': (
            'Vodnár prináša nekonvenčné myslenie, reformný impulz a orientáciu na komunitu. '
            'Astrologicky ukazuje, kde sa oslobodzuješ od starých vzorcov.'
        ),
        'challenge': 'Citový odstup, vzdor voči autorite a extrémny racionalizmus.',
        'advice': 'Spájaj originalitu s empatiou, aby zmena bola nielen správna, ale aj prijateľná.',
    },
    'pisces': {
        'name': 'Ryby',
        'symbol': '♓',
        'color': '#ff88d6',
        'date_range': '19.2. – 20.3.',
        'element': 'Voda',
        'modality': 'Premenlivé',
        'ruler': 'Neptún (tradične Jupiter)',
        'keywords': ['intuícia', 'súcit', 'imaginácia'],
        'theme': 'Archetyp rozpustenia: citlivosť na jemné signály a hlbokú empatiu.',
        'description': (
            'Ryby otvárajú tvorivosť, spiritualitu a schopnosť vnímať medzi riadkami. '
            'V horoskope ukazujú, kde sa učíš rozlišovať medzi inšpiráciou a ilúziou.'
        ),
        'challenge': 'Nejasné hranice, únikové stratégie a preberanie cudzích emócií.',
        'advice': 'Chráň svoje hranice a uzemňuj intuíciu cez konkrétne denné návyky.',
    },
}

PLANET_LEXICON = {
    'sun': {
        'keywords': ['identita', 'vôľa', 'životná sila'],
        'description': (
            'Slnko ukazuje, kým sa vedome stávaš. Hovorí o sebahodnote, smerovaní a potrebe žiť autenticky. '
            'V tranzitoch zvýrazňuje témy sebarealizácie, autority a osobného rozhodnutia.'
        ),
        'focus': 'Sebavyjadrenie, ego, životný smer, vitalita.',
    },
    'moon': {
        'keywords': ['emócie', 'bezpečie', 'vnútorný svet'],
        'description': (
            'Mesiac reprezentuje citové reakcie, potrebu istoty a podvedomé návyky. '
            'V tranzitoch aktivuje náladu, rodinné témy, potrebu oddychu a starostlivosti.'
        ),
        'focus': 'Emočné potreby, domov, intuícia, vnútorný rytmus.',
    },
    'mercury': {
        'keywords': ['myslenie', 'komunikácia', 'učenie'],
        'description': (
            'Merkúr opisuje spôsob, akým spracúvaš informácie a komunikuješ. '
            'V tranzitoch sa prejavuje v rozhovoroch, rozhodovaní, vyjednávaní a mentálnej agilite.'
        ),
        'focus': 'Reč, logika, písanie, obchod, mobility.',
    },
    'venus': {
        'keywords': ['vzťahy', 'hodnoty', 'príťažlivosť'],
        'description': (
            'Venuša ukazuje, čo považuješ za krásne a hodnotné. '
            'V tranzitoch rieši lásku, blízkosť, vkus, financie a schopnosť prijímať potešenie.'
        ),
        'focus': 'Partnerstvá, estetika, peniaze, harmónia.',
    },
    'mars': {
        'keywords': ['akcia', 'odvaha', 'hranice'],
        'description': (
            'Mars reprezentuje energiu, ktorou konáš a presadzuješ svoju vôľu. '
            'V tranzitoch prináša pohyb, tlak na rozhodnutie, súťaženie a niekedy konflikt.'
        ),
        'focus': 'Motivácia, výkon, hnev, sexualita, iniciatíva.',
    },
    'jupiter': {
        'keywords': ['rast', 'zmysel', 'expanzia'],
        'description': (
            'Jupiter ukazuje, kde sa rozširuje obzor a kde cítiš dôveru v život. '
            'V tranzitoch podporuje učenie, cestovanie, víziu a príležitosti pre rast.'
        ),
        'focus': 'Viera, filozofia, šťastie, rozvoj, veľkorysosť.',
    },
    'saturn': {
        'keywords': ['disciplína', 'zodpovednosť', 'hranice'],
        'description': (
            'Saturn prináša realitu, štruktúru a lekcie trpezlivosti. '
            'V tranzitoch preveruje záväzky, nastavuje limity a buduje dlhodobú stabilitu.'
        ),
        'focus': 'Povinnosti, vytrvalosť, čas, autorita, zrelosť.',
    },
    'uranus': {
        'keywords': ['zmena', 'sloboda', 'inovácia'],
        'description': (
            'Urán je princíp prebudenia a oslobodenia od zastaraných vzorcov. '
            'V tranzitoch prináša náhle obraty, prekvapenia a tlak na autenticitu.'
        ),
        'focus': 'Nezávislosť, originalita, revolúcia, prelom.',
    },
    'neptune': {
        'keywords': ['intuícia', 'spiritualita', 'ilúzia'],
        'description': (
            'Neptún rozpúšťa pevné hranice a otvára citlivosť na jemné vrstvy reality. '
            'V tranzitoch môže priniesť inšpiráciu, ale aj nejasnosť alebo idealizáciu.'
        ),
        'focus': 'Sny, empatia, umenie, mystika, dezilúzia.',
    },
    'pluto': {
        'keywords': ['transformácia', 'moc', 'obnova'],
        'description': (
            'Pluto ide do hĺbky a odhaľuje to, čo je skryté. '
            'V tranzitoch spúšťa intenzívnu premenu, koniec starých štruktúr a vznik novej sily.'
        ),
        'focus': 'Psychologická hĺbka, tieň, regenerácia, kontrola.',
    },
}

ASPECT_LEXICON = {
    'conjunction': {
        'angle': '0°',
        'tone': 'silná koncentrácia energie',
        'description': (
            'Konjunkcia spája dve energie do jedného bodu. Môže byť veľmi tvorivá aj intenzívna, '
            'podľa povahy planét. Téma je výrazná, neprehliadnuteľná a žiada vedomé uchopenie.'
        ),
    },
    'sextile': {
        'angle': '60°',
        'tone': 'podporný, spolupracujúci tok',
        'description': (
            'Sextil prináša príležitosť, ktorú treba aktívne využiť. '
            'Je harmonický, praktický a často podporuje učenie, kontakty a plynulý pokrok.'
        ),
    },
    'square': {
        'angle': '90°',
        'tone': 'napätie, tlak na akciu',
        'description': (
            'Kvadratúra odhaľuje konflikt dvoch princípov. '
            'Toto napätie však vie byť mimoriadne tvorivé, ak vedie k zmene návykov a lepším rozhodnutiam.'
        ),
    },
    'trine': {
        'angle': '120°',
        'tone': 'plynulá harmónia',
        'description': (
            'Trigón podporuje prirodzený tok a ľahkosť. '
            'Veci idú hladšie, no stále je dôležité tento priaznivý potenciál vedome nasmerovať.'
        ),
    },
    'opposition': {
        'angle': '180°',
        'tone': 'polarita a zrkadlenie',
        'description': (
            'Opozícia ukazuje dve strany jednej osi. '
            'Prináša konfrontáciu, ktorá učí rovnováhe medzi extrémami a lepšiemu pochopeniu vzťahov.'
        ),
    },
}


def _mask_email(email):
    if not email or '@' not in email:
        return ''
    local, domain = email.split('@', 1)
    if len(local) <= 1:
        masked_local = '*'
    elif len(local) == 2:
        masked_local = local[0] + '*'
    else:
        masked_local = local[:2] + ('*' * (len(local) - 2))
    return f"{masked_local}@{domain}"


def _send_verification_email(request, user):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse('transits:verify_email_confirm', kwargs={'uidb64': uidb64, 'token': token})
    )
    context = {
        'user': user,
        'verify_url': verify_url,
        'domain': request.get_host(),
    }
    text_body = render_to_string('registration/verify_email.txt', context)
    html_body = render_to_string('registration/verify_email.html', context)
    msg = EmailMultiAlternatives(
        subject='Pochop.sk - potvrdenie e-mailu',
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    msg.attach_alternative(html_body, 'text/html')
    msg.send(fail_silently=False)


def _has_gemini_key():
    return has_gemini_key()


def _set_analysis_error(profile_id, message):
    with ANALYSIS_STATE_LOCK:
        if message:
            ANALYSIS_LAST_ERROR[profile_id] = message
        else:
            ANALYSIS_LAST_ERROR.pop(profile_id, None)


def _get_analysis_error(profile_id):
    with ANALYSIS_STATE_LOCK:
        return ANALYSIS_LAST_ERROR.get(profile_id)


def _is_analysis_in_progress(profile_id):
    with ANALYSIS_STATE_LOCK:
        return profile_id in ANALYSIS_IN_PROGRESS


def _unlock_profile_with_password(request, profile, raw_password):
    """Odvodí user key z hesla a uloží ho do session."""
    if not request or not profile or not raw_password or not profile.birth_data_salt:
        return None
    try:
        profile.migrate_legacy_birth_data(raw_password)
        profile.save()
        key_b64 = derive_user_key_b64(raw_password, profile.birth_data_salt)
        # Validuj, že dešifrovanie funguje (ak má profil šifrované dáta).
        if profile.birth_date_encrypted and not profile.decrypt_birth_data(key_b64):
            return None
        store_profile_key_in_session(request.session, profile.pk, key_b64)
        return key_b64
    except Exception:
        return None


def _get_profile_birth_data(profile, request=None):
    """Vráti dešifrované birth dáta (session key) alebo legacy fallback."""
    if request and hasattr(request, 'session'):
        key_b64 = get_profile_key_from_session(request.session, profile.pk)
        if key_b64:
            decrypted = profile.decrypt_birth_data(key_b64=key_b64)
            if decrypted:
                return decrypted
    return profile.decrypt_birth_data(key_b64=None)


def _get_profile_birth_labels(profile, request=None):
    birth = _get_profile_birth_data(profile, request=request)
    if not birth:
        return {
            'birth_date': 'súkromné',
            'birth_time': 'súkromné',
            'birth_place': 'súkromné',
        }
    return {
        'birth_date': birth['birth_date'].strftime('%d.%m.%Y'),
        'birth_time': birth['birth_time'].strftime('%H:%M'),
        'birth_place': birth['birth_place'],
    }


# ═══════════════════════════════════════════
# Hlavná stránka a auth
# ═══════════════════════════════════════════

def index(request):
    """Hlavná stránka - landing alebo redirect na timeline."""
    if request.user.is_authenticated:
        # Redirect na timeline len ak má profil, inak zobraziť landing
        if hasattr(request.user, 'natal_profile'):
            return redirect('transits:timeline')

    today = datetime.now(ZoneInfo(MOMENT_TZ)).date()
    moment_report = (
        MomentReport.objects.filter(report_date=today).first()
        or MomentReport.objects.order_by('-report_date').first()
    )

    context = {}
    if moment_report:
        context = {
            'landing_moment_report': moment_report,
            'landing_moment_planets_json': json.dumps(moment_report.planets_json, ensure_ascii=False),
            'landing_moment_aspects_json': json.dumps(moment_report.aspects_json, ensure_ascii=False),
        }
    return render(request, 'transits/index.html', context)


def moment_overview(request):
    """Verejná stránka s denným astrologickým rozborom okamihu."""
    report = get_or_generate_moment_report()
    return render(request, 'transits/moment.html', {
        'report_date': report.report_date,
        'moment_planets_json': json.dumps(report.planets_json, ensure_ascii=False),
        'moment_aspects_json': json.dumps(report.aspects_json, ensure_ascii=False),
        'moment_ai_json': json.dumps(report.ai_report_json, ensure_ascii=False),
        'moment_generated_at': report.updated_at,
    })


def lexikon(request):
    """Verejný astrologický lexikón s planétami, aspektmi a tranzitmi."""
    planet_order_idx = {k: i for i, k in enumerate(PLANET_ORDER)}
    aspect_order_idx = {k: i for i, k in enumerate(ASPECT_ORDER)}

    grouped = {k: [] for k in PLANET_ORDER}
    seen = set()
    transit_ids = set()
    for transit, natal, aspect, effect, text in TRANSIT_DATA:
        key = (transit, natal, aspect)
        if key in seen:
            continue
        seen.add(key)
        row_id = f"transit-{transit}-{aspect}-{natal}"
        transit_ids.add(row_id)
        grouped.setdefault(transit, []).append({
            'id': row_id,
            'transit': transit,
            'natal': natal,
            'aspect': aspect,
            'effect': effect,
            'text': text,
            'transit_name': PLANET_NAMES_SK.get(transit, transit.title()),
            'natal_name': PLANET_NAMES_SK.get(natal, natal.title()),
            'aspect_name': ASPECT_NAMES_SK.get(aspect, aspect),
            'transit_symbol': PLANET_SYMBOLS.get(transit, ''),
            'natal_symbol': PLANET_SYMBOLS.get(natal, ''),
            'aspect_symbol': ASPECT_SYMBOLS.get(aspect, ''),
        })

    transit_groups = []
    for transit_key in PLANET_ORDER:
        rows = grouped.get(transit_key, [])
        rows.sort(key=lambda r: (
            planet_order_idx.get(r['natal'], 999),
            aspect_order_idx.get(r['aspect'], 999),
        ))
        transit_groups.append({
            'key': transit_key,
            'name': PLANET_NAMES_SK.get(transit_key, transit_key.title()),
            'symbol': PLANET_SYMBOLS.get(transit_key, ''),
            'count': len(rows),
            'items': rows,
        })

    planet_cards = []
    for key in PLANET_ORDER:
        info = PLANET_LEXICON.get(key, {})
        planet_cards.append({
            'id': f"planet-{key}",
            'key': key,
            'name': PLANET_NAMES_SK.get(key, key.title()),
            'symbol': PLANET_SYMBOLS.get(key, ''),
            'keywords': info.get('keywords', []),
            'description': info.get('description', ''),
            'focus': info.get('focus', ''),
        })

    aspect_cards = []
    for key in ASPECT_ORDER:
        info = ASPECT_LEXICON.get(key, {})
        aspect_cards.append({
            'id': f"aspect-{key}",
            'key': key,
            'name': ASPECT_NAMES_SK.get(key, key).capitalize(),
            'symbol': ASPECT_SYMBOLS.get(key, ''),
            'angle': info.get('angle', ''),
            'tone': info.get('tone', ''),
            'description': info.get('description', ''),
        })

    zodiac_cards = []
    for key in ZODIAC_ORDER:
        info = ZODIAC_LEXICON.get(key, {})
        zodiac_cards.append({
            'id': f"sign-{key}",
            'key': key,
            'name': info.get('name', key.title()),
            'symbol': info.get('symbol', ''),
            'color': info.get('color', '#c8a6ff'),
            'date_range': info.get('date_range', ''),
            'element': info.get('element', ''),
            'modality': info.get('modality', ''),
            'ruler': info.get('ruler', ''),
            'keywords': info.get('keywords', []),
            'theme': info.get('theme', ''),
            'description': info.get('description', ''),
            'challenge': info.get('challenge', ''),
            'advice': info.get('advice', ''),
        })

    focus_target_id = ''
    planet_target = (request.GET.get('planet') or '').strip().lower()
    aspect_target = (request.GET.get('aspect') or '').strip().lower()
    sign_target = (request.GET.get('sign') or '').strip().lower()
    transit_target = (request.GET.get('transit') or '').strip().lower()

    if planet_target in PLANET_NAMES_SK:
        focus_target_id = f"planet-{planet_target}"
    if aspect_target in ASPECT_NAMES_SK:
        focus_target_id = f"aspect-{aspect_target}"
    if sign_target in ZODIAC_LEXICON:
        focus_target_id = f"sign-{sign_target}"
    if transit_target:
        parts = transit_target.split('-')
        if len(parts) == 3:
            maybe_id = f"transit-{parts[0]}-{parts[1]}-{parts[2]}"
            if maybe_id in transit_ids:
                focus_target_id = maybe_id

    return render(request, 'transits/lexikon.html', {
        'zodiac_cards': zodiac_cards,
        'planet_cards': planet_cards,
        'aspect_cards': aspect_cards,
        'transit_groups': transit_groups,
        'transit_total_count': len(seen),
        'focus_target_id': focus_target_id,
    })


@ensure_csrf_cookie
def register_view(request):
    """Registrácia s natálnymi údajmi (AJAX POST)."""
    if request.user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'redirect': '/timeline/'})
        return redirect('transits:timeline')

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        form = RegistrationForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=cd['username'],
                        email=cd['email'],
                        password=cd['password1'],
                        is_active=False,
                    )
                    tz = get_timezone_for_location(cd['birth_lat'], cd['birth_lon'])
                    profile = NatalProfile.objects.create(
                        user=user,
                        name=cd['username'],
                        gender=cd.get('gender') or 'male',
                        timezone=tz,
                    )
                    # Ulož PII zašifrovane user heslom.
                    profile.set_encrypted_birth_data(
                        raw_password=cd['password1'],
                        birth_date=cd['birth_date'],
                        birth_time=cd['birth_time'],
                        birth_place=cd['birth_place'],
                        birth_lat=cd['birth_lat'],
                        birth_lon=cd['birth_lon'],
                    )
                    # Predpočítaj natal pozície/chart, aby runtime nepotreboval dešifrovať PII.
                    profile.natal_positions_json = calculate_natal_positions(
                        cd['birth_date'],
                        cd['birth_time'],
                        cd['birth_lat'],
                        cd['birth_lon'],
                        tz,
                    )
                    profile.natal_chart_json = calculate_natal_chart(
                        cd['birth_date'],
                        cd['birth_time'],
                        cd['birth_lat'],
                        cd['birth_lon'],
                        tz,
                    )
                    profile.save()
                    _send_verification_email(request, user)
            except Exception as exc:
                logger.error("Registrácia: odoslanie verifikačného e-mailu zlyhalo: %s", exc)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'errors': {
                            '__all__': [
                                'Nepodarilo sa odoslať potvrdzovací e-mail. Skúste to prosím neskôr.'
                            ]
                        },
                    }, status=500)
                form.add_error(
                    None,
                    'Nepodarilo sa odoslať potvrdzovací e-mail. Skúste to prosím neskôr.',
                )
            else:
                sent_url = f"{reverse('transits:verify_email_sent')}?{urlencode({'email': cd['email']})}"
                if is_ajax:
                    return JsonResponse({'success': True, 'redirect': sent_url})
                return redirect(sent_url)
        else:
            if is_ajax:
                errors = {}
                for field, errs in form.errors.items():
                    errors[field] = [str(e) for e in errs]
                return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = RegistrationForm()

    return render(request, 'transits/register.html', {'form': form})


def _start_analysis_generation(profile_id):
    """Spustí generovanie analýz v background vlákne."""
    if not _has_gemini_key():
        _set_analysis_error(profile_id, 'Gemini API kľúč nie je nakonfigurovaný.')
        return False

    with ANALYSIS_STATE_LOCK:
        if profile_id in ANALYSIS_IN_PROGRESS:
            return False
        ANALYSIS_IN_PROGRESS.add(profile_id)
        ANALYSIS_LAST_ERROR.pop(profile_id, None)

    worker = threading.Thread(
        target=_generate_and_save_analyses_background,
        args=(profile_id,),
        daemon=True,
    )
    try:
        worker.start()
    except Exception as e:
        with ANALYSIS_STATE_LOCK:
            ANALYSIS_IN_PROGRESS.discard(profile_id)
        _set_analysis_error(profile_id, 'Nepodarilo sa spustiť generovanie analýzy.')
        logger.error(f"Nepodarilo sa spustiť background worker pre profil {profile_id}: {e}")
        return False
    return True


def _generate_and_save_analyses_background(profile_id):
    """Načíta profil a bezpečne vygeneruje analýzy mimo requestu."""
    close_old_connections()
    try:
        profile = NatalProfile.objects.get(pk=profile_id)
        success = _generate_and_save_analyses(profile)
        if success:
            _set_analysis_error(profile_id, None)
        elif not _has_gemini_key():
            _set_analysis_error(profile_id, 'Gemini API kľúč nie je nakonfigurovaný.')
        else:
            _set_analysis_error(profile_id, 'Generovanie analýzy zlyhalo. Skúste obnoviť stránku.')
    except NatalProfile.DoesNotExist:
        logger.warning(f"Profil {profile_id} neexistuje, analýzu nie je možné vygenerovať.")
        _set_analysis_error(profile_id, 'Profil neexistuje, analýzu nie je možné vygenerovať.')
    except Exception as e:
        logger.error(f"Background generovanie analýz zlyhalo pre profil {profile_id}: {e}")
        _set_analysis_error(profile_id, 'Interná chyba pri generovaní analýzy.')
    finally:
        with ANALYSIS_STATE_LOCK:
            ANALYSIS_IN_PROGRESS.discard(profile_id)
        close_old_connections()


def login_view(request):
    """Prihlásenie."""
    if request.user.is_authenticated:
        return redirect('transits:timeline')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            raw_password = form.cleaned_data.get('password')
            try:
                profile = user.natal_profile
                _unlock_profile_with_password(request, profile, raw_password)
            except (NatalProfile.DoesNotExist, AttributeError):
                pass
            return redirect('transits:timeline')
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        if username and password:
            maybe_user = User.objects.filter(username=username).first()
            if maybe_user and not maybe_user.is_active and maybe_user.check_password(password):
                form.add_error(
                    None,
                    'Účet ešte nie je overený cez e-mail. Skontrolujte schránku alebo požiadajte o nový potvrdzovací e-mail.',
                )
    else:
        form = LoginForm()

    return render(request, 'transits/login.html', {'form': form})


def logout_view(request):
    """Odhlásenie."""
    logout(request)
    return redirect('transits:index')


def verify_email_sent_view(request):
    email = (request.GET.get('email') or '').strip().lower()
    return render(request, 'transits/verify_email_sent.html', {
        'masked_email': _mask_email(email),
    })


def verify_email_confirm_view(request, uidb64, token):
    user = None
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])
        return render(request, 'transits/verify_email_confirm.html', {
            'verified': True,
        })

    return render(request, 'transits/verify_email_confirm.html', {
        'verified': False,
    }, status=400)


@ensure_csrf_cookie
def resend_verification_view(request):
    sent = False
    form = ResendVerificationForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email'].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user and not user.is_active and user.email:
            try:
                _send_verification_email(request, user)
            except Exception as exc:
                logger.error(
                    "Resend verification failed for user=%s: %s",
                    user.pk,
                    exc,
                )
        sent = True

    return render(request, 'transits/verify_email_resend.html', {
        'form': form,
        'sent': sent,
    })


@login_required(login_url='transits:login')
@ensure_csrf_cookie
def password_change_view(request):
    """Bezpečná zmena hesla + re-encrypt citlivých údajov."""
    if request.method == 'POST':
        form = StyledPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            old_password = form.cleaned_data['old_password']
            new_password = form.cleaned_data['new_password1']
            profile = None
            try:
                profile = request.user.natal_profile
            except (NatalProfile.DoesNotExist, AttributeError):
                profile = None

            try:
                with transaction.atomic():
                    if profile and not profile.reencrypt_birth_data(
                        new_raw_password=new_password,
                        old_raw_password=old_password,
                    ):
                        raise ValueError('PII re-encryption failed')
                    if profile:
                        profile.save()
                    user = form.save()
            except ValueError:
                form.add_error(
                    None,
                    'Nepodarilo sa bezpečne prešifrovať citlivé údaje. Skúste to znovu.',
                )
            except Exception as exc:
                logger.error(
                    "Zmena hesla zlyhala pre user=%s: %s",
                    request.user.pk,
                    exc,
                )
                form.add_error(
                    None,
                    'Interná chyba pri zmene hesla. Skúste to prosím znovu.',
                )
            else:
                update_session_auth_hash(request, user)
                if profile:
                    _unlock_profile_with_password(request, profile, new_password)
                return redirect('transits:password_change_done')
    else:
        form = StyledPasswordChangeForm(request.user)

    return render(request, 'transits/password_change.html', {'form': form})


@login_required(login_url='transits:login')
def password_change_done_view(request):
    return render(request, 'transits/password_change_done.html')


class PochopPasswordResetView(PasswordResetView):
    template_name = 'transits/password_reset_form.html'
    form_class = StyledPasswordResetForm
    email_template_name = 'registration/password_reset_email.txt'
    subject_template_name = 'registration/password_reset_subject.txt'
    success_url = reverse_lazy('transits:password_reset_done')


class PochopPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'transits/password_reset_done.html'


class PochopPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'transits/password_reset_confirm.html'
    form_class = StyledSetPasswordForm
    success_url = reverse_lazy('transits:password_reset_complete')

    def form_valid(self, form):
        response = super().form_valid(form)
        new_password = form.cleaned_data.get('new_password1')
        profile = None
        try:
            profile = self.user.natal_profile
        except (NatalProfile.DoesNotExist, AttributeError):
            profile = None

        if profile and new_password:
            try:
                with transaction.atomic():
                    if profile.reencrypt_birth_data(new_raw_password=new_password):
                        profile.save()
                    else:
                        logger.warning(
                            "Reset hesla pre user=%s prebehol, ale PII re-encrypt sa nepodaril.",
                            self.user.pk,
                        )
            except Exception as exc:
                logger.error(
                    "Reset hesla: PII re-encrypt zlyhal pre user=%s: %s",
                    self.user.pk,
                    exc,
                )
        return response


class PochopPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'transits/password_reset_complete.html'


# ═══════════════════════════════════════════
# Cities API
# ═══════════════════════════════════════════

def api_cities(request):
    """API pre vyhľadávanie slovenských obcí."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    cities = SlovakCity.objects.filter(name__icontains=q)[:15]
    results = [
        {
            'id': c.pk,
            'name': c.name,
            'district': c.district,
            'lat': c.lat,
            'lon': c.lon,
            'label': f"{c.name} (okres {c.district})",
        }
        for c in cities
    ]
    return JsonResponse({'results': results})


# ═══════════════════════════════════════════
# Timeline
# ═══════════════════════════════════════════

@login_required(login_url='transits:login')
@ensure_csrf_cookie
def timeline(request, profile_id=None):
    """Stránka s timeline tranzitov."""
    profile = None
    transits_data = []

    if profile_id:
        profile = get_object_or_404(NatalProfile, pk=profile_id)
    else:
        # Použi profil prihláseného usera
        try:
            profile = request.user.natal_profile
        except (NatalProfile.DoesNotExist, AttributeError):
            # User nemá profil - presmeruj na hlavnú stránku
            logout(request)
            return redirect('transits:index')

    if profile:
        transits_data = _compute_transits_for_profile(profile, request=request)
    birth_labels = _get_profile_birth_labels(profile, request=request) if profile else {
        'birth_date': 'súkromné',
        'birth_time': 'súkromné',
        'birth_place': 'súkromné',
    }

    return render(request, 'transits/timeline.html', {
        'profile': profile,
        'transits': json.dumps(transits_data, ensure_ascii=False),
        'transits_list': transits_data,
        'profile_birth_date': birth_labels['birth_date'],
        'profile_birth_time': birth_labels['birth_time'],
        'profile_birth_place': birth_labels['birth_place'],
    })


def api_transits(request, profile_id):
    """API endpoint pre získanie tranzitov (JSON)."""
    profile = get_object_or_404(NatalProfile, pk=profile_id)
    transits_data = _compute_transits_for_profile(profile, request=request)
    birth_labels = _get_profile_birth_labels(profile, request=request)
    return JsonResponse({'transits': transits_data, 'profile': {
        'name': profile.name,
        'birth_date': birth_labels['birth_date'],
        'birth_time': birth_labels['birth_time'],
        'birth_place': birth_labels['birth_place'],
    }})


def _compute_transits_for_profile(profile, request=None):
    """Vypočíta tranzity pre profil a pridá texty z databázy."""
    natal_positions = profile.natal_positions_json
    if not natal_positions:
        birth = _get_profile_birth_data(profile, request=request)
        if not birth:
            logger.warning("Profil %s nemá dostupné dešifrované narodenie ani natal_positions.", profile.pk)
            return []
        natal_positions = calculate_natal_positions(
            birth['birth_date'],
            birth['birth_time'],
            birth['birth_lat'],
            birth['birth_lon'],
            birth.get('timezone') or profile.timezone,
        )
        profile.natal_positions_json = natal_positions
        profile.save(update_fields=['natal_positions_json', 'updated_at'])

    today = date.today()
    raw_transits = calculate_transits(
        natal_positions,
        today,
        days_range=30,
        timezone_str=profile.timezone,
    )

    # Pridáme texty z databázy a symboly
    result = []
    for t in raw_transits:
        # Nájdeme výklad z databázy
        try:
            aspect_obj = TransitAspect.objects.get(
                transit_planet=t['transit_planet'],
                natal_planet=t['natal_planet'],
                aspect_type=t['aspect'],
            )
            text = aspect_obj.display_text
            effect = aspect_obj.effect
        except TransitAspect.DoesNotExist:
            text = f"{t['aspect_name_sk']} t.{t['transit_planet_name_sk']} - n.{t['natal_planet_name_sk']}"
            effect = t['default_effect']

        transit_info = {
            'id': f"{t['transit_planet']}_{t['natal_planet']}_{t['aspect']}",
            'title': (
                f"{t['aspect_name_sk']} "
                f"t.{t['transit_planet_name_sk']} - "
                f"n.{t['natal_planet_name_sk']}"
            ),
            'transit_symbol': PLANET_SYMBOLS.get(t['transit_planet'], ''),
            'natal_symbol': PLANET_SYMBOLS.get(t['natal_planet'], ''),
            'aspect_symbol': ASPECT_SYMBOLS.get(t['aspect'], ''),
            'text': text,
            'effect': effect,
            'orb': t['orb'],
            'orb_limit': t['orb_limit'],
            'intensity': t['intensity'],
            'start_date': t['start_date'],
            'end_date': t['end_date'],
            'exact_date': t['exact_date'],
            'start_date_iso': t['start_date_iso'],
            'end_date_iso': t['end_date_iso'],
            'exact_date_iso': t['exact_date_iso'],
            'transit_planet': t['transit_planet'],
            'natal_planet': t['natal_planet'],
            'aspect': t['aspect'],
        }
        result.append(transit_info)

    return result


# ═══════════════════════════════════════════
# Natálna analýza - Gemini AI
# ═══════════════════════════════════════════

NATAL_SYSTEM_PROMPT = """Si skúsený astrológ s hlbokým porozumením natálnych horoskopov. Tvojou úlohou je poskytnúť komplexnú, personalizovanú natálnu analýzu v slovenčine.

PRAVIDLÁ:
- Píš v slovenčine, oslovuj čitateľa priamo (ty-forma)
- Buď konkrétny, nie všeobecný. Vyhýbaj sa klišé typu "si citlivý človek"
- Kombinuj vplyvy planét, aspektov, elementov a domov
- Analyzuj VZÁJOMNÉ pôsobenie aspektov, nie len jednotlivé izolovane
- Zameraj sa na praktické postrehy, nie na abstraktnú ezoteriu
- Buď diplomatický pri ťažkých aspektoch - formuluj ich ako výzvy k rastu
- Odpoveď má byť rozsiahla, informatívna a hodnotná
- Nepoužívaj interné poznámky, planning texty ani anglické značky typu "Draft", "Perfect", "Focus:"
- Nepoužívaj markdown code bloky, nevracaj meta-komentáre o tom ako odpoveď tvoríš

FORMÁT ODPOVEDE (použi PRESNE tieto nadpisy):

SLNEČNÉ ZNAMENIE:
(2-3 vety o slnečnom znamení a jeho prejavoch v kontexte celého horoskopu)

ASCENDENT A VONKAJŠÍ PREJAV:
(2-3 vety - ako ťa vidia ostatní, prvý dojem, vzhľad, štýl komunikácie)

EMOCIONÁLNY SVET:
(2-3 vety o Mesiaci, citový život, vnútorné potreby, reakcie na stres)

KOMUNIKÁCIA A MYSLENIE:
(2-3 vety o Merkúri - štýl myslenia, učenie sa, spôsob vyjadrovania)

VZŤAHY A LÁSKA:
(2-3 vety o Venuši - čo ťa priťahuje, ako miluješ, hodnoty)

ENERGIA A MOTIVÁCIA:
(2-3 vety o Marse - ako presadzuješ svoju vôľu, drive, temperament)

RAST A ŠŤASTIE:
(2-3 vety o Jupitere - kde nachádzaš šťastie, expanzia, optimizmus)

VÝZVY A DISCIPLÍNA:
(2-3 vety o Saturne - životné lekcie, kde musíš pracovať na sebe)

SILNÉ STRÁNKY:
- (konkrétna silná stránka 1)
- (konkrétna silná stránka 2)
- (konkrétna silná stránka 3)
- (konkrétna silná stránka 4)
- (konkrétna silná stránka 5)

VÝZVY NA PRÁCU:
- (konkrétna výzva 1)
- (konkrétna výzva 2)
- (konkrétna výzva 3)

ŽIVOTNÁ CESTA:
(3-4 vety - celková syntéza horoskopu, čo je tvojím životným poslaním, kam smeruješ)"""


def _gender_addressing_instruction(profile):
    """Vráti jazykový pokyn pre oslovovanie podľa pohlavia profilu."""
    if getattr(profile, 'gender', 'male') == 'female':
        return "Oslovuj používateľku v ženskom rode (napr. 'si pripravená', 'máš otvorenú tému')."
    return "Oslovuj používateľa v mužskom rode (napr. 'si pripravený', 'máš otvorenú tému')."


def _build_natal_prompt(profile, chart):
    """Zostaví detailný prompt pre natálnu analýzu."""
    planets = chart['planets']
    asc = chart['ascendant']
    mc = chart['midheaven']
    aspects = chart['aspects']
    elements = chart['elements']
    modalities = chart['modalities']

    lines = [
        f"NATÁLNY HOROSKOP pre: {profile.name}",
        f"Profil hash: {profile.public_hash or 'n/a'}",
        f"Pohlavie profilu: {profile.get_gender_display()}",
        f"Jazykový pokyn: {_gender_addressing_instruction(profile)}",
        "",
        "═══ POZÍCIE PLANÉT ═══",
    ]

    for key, p in planets.items():
        lines.append(f"  {p['name_sk']:10s} {p['degree']:5.1f}° {p['sign']:12s} {p['symbol']}")

    lines.append("")
    lines.append(f"  Ascendent   {asc['degree']:.1f}° {asc['sign']} {asc['symbol']}")
    lines.append(f"  MC (Medium Coeli)  {mc['degree']:.1f}° {mc['sign']} {mc['symbol']}")

    lines.append("")
    lines.append("═══ ASPEKTY ═══")
    for a in aspects:
        lines.append(f"  {a['planet1_sk']} {a['aspect_sk']} {a['planet2_sk']} (orb {a['orb']}°)")

    lines.append("")
    lines.append("═══ ROZLOŽENIE ELEMENTOV ═══")
    for elem, count in elements.items():
        bar = '█' * count
        lines.append(f"  {elem:7s} {count} {bar}")

    lines.append("")
    lines.append("═══ ROZLOŽENIE MODALÍT ═══")
    for mod, count in modalities.items():
        bar = '█' * count
        lines.append(f"  {mod:11s} {count} {bar}")

    lines.append("")
    lines.append("Vytvor komplexnú natálnu analýzu podľa pokynov.")
    return "\n".join(lines)


def _parse_natal_response(text):
    """Parsuje natálnu analýzu z Gemini."""
    sections = []
    current_title = None
    current_lines = []

    section_map = {
        'SLNEČNÉ ZNAMENIE': ('sun', '☉'),
        'ASCENDENT A VONKAJŠÍ PREJAV': ('asc', '⬆'),
        'EMOCIONÁLNY SVET': ('moon', '☽'),
        'KOMUNIKÁCIA A MYSLENIE': ('mercury', '☿'),
        'VZŤAHY A LÁSKA': ('love', '♀'),
        'ENERGIA A MOTIVÁCIA': ('energy', '♂'),
        'RAST A ŠŤASTIE': ('growth', '♃'),
        'VÝZVY A DISCIPLÍNA': ('discipline', '♄'),
        'SILNÉ STRÁNKY': ('strengths', '💪'),
        'VÝZVY NA PRÁCU': ('challenges', '⚡'),
        'ŽIVOTNÁ CESTA': ('path', '✦'),
    }

    def flush():
        if current_title and current_title in section_map:
            sid, icon = section_map[current_title]
            content = '\n'.join(current_lines).strip()
            if content:
                is_list = any(line.strip().startswith('- ') for line in current_lines if line.strip())
                items = []
                text_content = ''
                if is_list:
                    items = [l.strip()[2:].strip() for l in current_lines if l.strip().startswith('- ')]
                else:
                    text_content = content
                sections.append({
                    'id': sid,
                    'icon': icon,
                    'title': current_title.title(),
                    'text': text_content,
                    'items': items,
                })

    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped:
            if current_title:
                current_lines.append('')
            continue

        normalized = stripped.replace('**', '').strip()
        upper = normalized.upper().rstrip(':')
        if upper in section_map:
            flush()
            current_title = upper
            current_lines = []
            # Check for inline content after ":"
            after_colon = normalized.split(':', 1)
            if len(after_colon) > 1 and after_colon[1].strip():
                current_lines.append(after_colon[1].strip())
        elif current_title:
            current_lines.append(normalized)

    flush()
    if sections:
        return sections

    # Fallback: ak model nedodal sekcie, zachovaj aspoň text
    compact = ' '.join((text or '').split()).strip()
    if compact:
        return [{
            'id': 'summary',
            'icon': '✦',
            'title': 'Natálna analýza',
            'text': compact,
            'items': [],
        }]
    return sections


def _fallback_natal_sections(profile, chart):
    """Deterministický fallback natálnej analýzy pri zlyhaní AI formátu."""
    planets = chart.get('planets', {})
    sun = planets.get('sun', {})
    moon = planets.get('moon', {})
    asc = chart.get('ascendant', {})
    elements = chart.get('elements', {})
    dominant = max(elements, key=elements.get) if elements else 'Rovnováha'

    return [
        {
            'id': 'sun',
            'icon': '☉',
            'title': 'Slnečné znamenie',
            'text': (
                f"Tvoje jadrové nastavenie nesie energiu znamenia {sun.get('sign', '—')}. "
                f"Najsilnejšie sa prejavuje cez štýl, v ktorom robíš rozhodnutia a smeruješ svoju vôľu."
            ),
            'items': [],
        },
        {
            'id': 'moon',
            'icon': '☽',
            'title': 'Emocionálny svet',
            'text': (
                f"Mesiac v znamení {moon.get('sign', '—')} ukazuje, ako spracúvaš emócie a stres. "
                f"Vhodné je vedome prepínať medzi výkonom a regeneráciou."
            ),
            'items': [],
        },
        {
            'id': 'asc',
            'icon': '⬆',
            'title': 'Ascendent a prejav',
            'text': (
                f"Ascendent v znamení {asc.get('sign', '—')} určuje prvý dojem a spôsob, akým vstupuješ do nových situácií."
            ),
            'items': [],
        },
        {
            'id': 'strengths',
            'icon': '💪',
            'title': 'Silné stránky',
            'text': '',
            'items': [
                f"Dominantný element: {dominant}.",
                'Schopnosť adaptovať sa podľa aktuálnej situácie.',
                'Potenciál pre dlhodobý osobný rast cez vedomé rozhodnutia.',
            ],
        },
    ]


def _natal_payload_is_valid(sections):
    """Basic kvalitatívny filter proti prompt-leak výstupom."""
    if not sections or not isinstance(sections, list):
        return False

    bad_markers = (
        'perfect',
        'draft',
        'sentences',
        'focus:',
        '*(sk)',
        'saturn in ',
        'vyzvy a disciplina',
        '**',
    )

    merged = ' '.join(
        (
            (s.get('title', '') + ' ' + s.get('text', '') + ' ' + ' '.join(s.get('items', [])))
            for s in sections
            if isinstance(s, dict)
        )
    ).lower()

    if not merged.strip():
        return False
    if any(marker in merged for marker in bad_markers):
        return False

    useful_sections = [s for s in sections if (s.get('text') or s.get('items'))]
    return len(useful_sections) >= 2


def _generate_and_save_analyses(profile, model_name=None):
    """
    Vygeneruje natálnu analýzu aj analýzu aspektov cez Gemini
    a uloží výsledky do profilu. Volá sa raz pri registrácii.
    """
    if not _has_gemini_key():
        logger.warning("Gemini API kľúč nie je nakonfigurovaný, preskakujem analýzy.")
        return False

    # Preferuj uložený chart (nevyžaduje dešifrovanie PII).
    chart = profile.natal_chart_json
    if not chart:
        birth = _get_profile_birth_data(profile, request=None)
        if not birth:
            logger.error(
                "Profil %s nemá chart ani dešifrovateľné birth dáta, analýzu nemožno zregenerovať.",
                profile.pk,
            )
            return False
        chart = calculate_natal_chart(
            birth['birth_date'],
            birth['birth_time'],
            birth['birth_lat'],
            birth['birth_lon'],
            birth.get('timezone') or profile.timezone,
        )
        profile.natal_chart_json = chart

    if not profile.natal_positions_json:
        birth = _get_profile_birth_data(profile, request=None)
        if birth:
            profile.natal_positions_json = calculate_natal_positions(
                birth['birth_date'],
                birth['birth_time'],
                birth['birth_lat'],
                birth['birth_lon'],
                birth.get('timezone') or profile.timezone,
            )

    active_model = get_gemini_model(model_name)

    # Predvyplníme deterministic fallbacky, aby UI nezostalo bez textu.
    parsed_natal = _fallback_natal_sections(profile, chart)
    parsed_aspects = _fallback_aspects_analysis(chart)

    # 1. Natálna analýza
    try:
        natal_prompt = _build_natal_prompt(profile, chart)
        natal_text = generate_gemini_text(
            model_name=active_model,
            contents=natal_prompt,
            system_instruction=NATAL_SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=2200,
            retries=2,
            timeout_seconds=60,
        )
        ai_natal = _parse_natal_response(natal_text)
        if _natal_payload_is_valid(ai_natal):
            parsed_natal = ai_natal
        else:
            logger.warning(
                "Natálna analýza pre %s mala slabú kvalitu, ponechávam fallback.",
                profile.name,
            )
    except GeminiLimitExceededError:
        logger.warning("Denný limit Gemini prekročený pri natálnej analýze (%s).", profile.name)
    except Exception as exc:
        logger.error("Natálna analýza Gemini zlyhala pre %s: %s", profile.name, exc)

    # 2. Analýza aspektov
    try:
        aspects_prompt = _build_aspects_prompt(profile, chart)
        aspects_text = generate_gemini_text(
            model_name=active_model,
            contents=aspects_prompt,
            system_instruction=ASPECTS_SYSTEM_PROMPT,
            temperature=0.65,
            max_output_tokens=3200,
            retries=2,
            timeout_seconds=70,
        )
        ai_aspects = _parse_aspects_response(aspects_text, chart['aspects'])
        if any((a.get('text') or '').strip() for a in ai_aspects):
            parsed_aspects = ai_aspects
        else:
            logger.warning(
                "Aspektová analýza pre %s je prázdna, ponechávam fallback.",
                profile.name,
            )
    except GeminiLimitExceededError:
        logger.warning("Denný limit Gemini prekročený pri aspektoch (%s).", profile.name)
    except Exception as exc:
        logger.error("Analýza aspektov Gemini zlyhala pre %s: %s", profile.name, exc)

    profile.natal_analysis_json = parsed_natal
    profile.natal_aspects_json = parsed_aspects

    try:
        profile.save()
    except Exception as exc:
        logger.error("Uloženie analýz zlyhalo pre %s: %s", profile.name, exc)
        return False

    if profile.has_analysis:
        logger.info(f"Analýzy vygenerované a uložené pre {profile.name}")
        return True
    logger.warning(f"Analýza pre {profile.name} je neúplná, vyžaduje ďalší pokus.")
    return False


@login_required(login_url='transits:login')
@ensure_csrf_cookie
def natal_analysis(request):
    """Stránka s natálnou analýzou používateľa."""
    try:
        profile = request.user.natal_profile
    except (NatalProfile.DoesNotExist, AttributeError):
        return redirect('transits:index')

    # Použi uložený chart alebo vypočítaj nový
    chart = profile.natal_chart_json
    if not chart:
        birth = _get_profile_birth_data(profile, request=request)
        if birth:
            chart = calculate_natal_chart(
                birth['birth_date'],
                birth['birth_time'],
                birth['birth_lat'],
                birth['birth_lon'],
                birth.get('timezone') or profile.timezone,
            )
            profile.natal_chart_json = chart
            profile.save(update_fields=['natal_chart_json', 'updated_at'])
        else:
            chart = {'planets': {}, 'aspects': [], 'elements': {}, 'modalities': {}, 'ascendant': {}, 'midheaven': {}}
    has_analysis = profile.has_analysis
    if not has_analysis:
        _start_analysis_generation(profile.pk)
    birth_labels = _get_profile_birth_labels(profile, request=request)

    return render(request, 'transits/natal.html', {
        'profile': profile,
        'chart': chart,
        'chart_json': json.dumps(chart, ensure_ascii=False),
        'analysis_sections': json.dumps(
            profile.natal_analysis_json or [], ensure_ascii=False
        ),
        'aspects_data': json.dumps(
            profile.natal_aspects_json or [], ensure_ascii=False
        ),
        'has_analysis': has_analysis,
        'analysis_can_generate': _has_gemini_key(),
        'analysis_error': _get_analysis_error(profile.pk),
        'profile_birth_date': birth_labels['birth_date'],
        'profile_birth_time': birth_labels['birth_time'],
        'profile_birth_place': birth_labels['birth_place'],
    })


@login_required(login_url='transits:login')
@require_http_methods(["GET"])
def api_natal_analysis_status(request):
    """Stav generovania natálnej analýzy pre polling vo fronte."""
    try:
        profile = request.user.natal_profile
    except (NatalProfile.DoesNotExist, AttributeError):
        return JsonResponse({
            'has_analysis': False,
            'in_progress': False,
            'can_generate': _has_gemini_key(),
            'started': False,
            'error': 'Profil neexistuje.',
        }, status=404)

    try:
        profile.refresh_from_db(fields=['natal_analysis_json', 'natal_aspects_json'])
        started = False
        if not profile.has_analysis and not _is_analysis_in_progress(profile.pk) and _has_gemini_key():
            started = _start_analysis_generation(profile.pk)
        return JsonResponse({
            'has_analysis': profile.has_analysis,
            'in_progress': _is_analysis_in_progress(profile.pk),
            'can_generate': _has_gemini_key(),
            'started': started,
            'error': _get_analysis_error(profile.pk),
        })
    except Exception as e:
        logger.error(f"Chyba API statusu natálnej analýzy pre profil {profile.pk}: {e}")
        return JsonResponse({
            'has_analysis': False,
            'in_progress': False,
            'can_generate': _has_gemini_key(),
            'started': False,
            'error': 'Nepodarilo sa načítať stav analýzy.',
        }, status=500)


# ═══════════════════════════════════════════
# Natálne aspekty - hlboká analýza Gemini AI
# ═══════════════════════════════════════════

ASPECTS_SYSTEM_PROMPT = """Si elitný astrológ s 30-ročnou praxou v hlbinnej psychologickej astrológii. Analyzuješ natálne aspekty s mimoriadnou hĺbkou a presnosťou.

PRAVIDLÁ:
- Píš v slovenčine, oslovuj čitateľa priamo (ty-forma)
- Každý aspekt analyzuj individuálne ALE v kontexte celého horoskopu
- Buď KONKRÉTNY: namiesto "si kreatívny" napíš "tvoja kreativita sa prejavuje cez originálne, nečakané nápady ktoré prichádzajú spontánne"
- Rozlišuj SILU aspektu podľa orbu: tesný orb (<1°) = dominantný vplyv, stredný (1-3°) = silný, širší (3-6°) = jemnejší
- Konjunkcia = zlúčenie energií (môže byť aj náročná!). Sextil/Trigón = talenty. Kvadratúra = vnútorné napätie a rast. Opozícia = polarita a integrácia.
- Pri ťažkých aspektoch (kvadratúra, opozícia) zdôrazni AJ ich transformačný potenciál
- Ak sú dva aspekty prepojené (zdieľajú planétu), poukaž na túto dynamiku
- NIKDY nepoužívaj frázy: "si citlivý", "máš silnú intuíciu", "si pracovitý" bez konkrétneho kontextu

Pre KAŽDÝ aspekt použi PRESNE tento formát:

ASPEKT: [Planéta1] [typ aspektu] [Planéta2]:
(3-5 viet hlbokej analýzy - psychologická dynamika, ako sa aspekt prejavuje v praxi, konkrétne situácie kde tento aspekt vystupuje, talenty alebo výzvy z neho plynúce)

Píš súvisle, každý aspekt ako ucelený odsek. Nepoužívaj odrážky vnútri aspektu."""


def _build_aspects_prompt(profile, chart):
    """Zostaví prompt pre hlbokú analýzu aspektov."""
    planets = chart['planets']
    aspects = chart['aspects']
    asc = chart['ascendant']

    lines = [
        f"NATÁLNY HOROSKOP: {profile.name}",
        f"Profil hash: {profile.public_hash or 'n/a'}",
        f"Pohlavie profilu: {profile.get_gender_display()}",
        f"Jazykový pokyn: {_gender_addressing_instruction(profile)}",
        f"Ascendent: {asc['degree']:.1f}° {asc['sign']}",
        "",
        "POZÍCIE PLANÉT (pre kontext):",
    ]
    for key, p in planets.items():
        lines.append(f"  {p['name_sk']} v {p['sign']} ({p['degree']:.1f}°)")

    lines.append("")
    lines.append("ASPEKTY NA ANALÝZU:")
    for i, a in enumerate(aspects, 1):
        orb_strength = "TESNÝ" if a['orb'] < 1.0 else "SILNÝ" if a['orb'] < 3.0 else "ŠIRŠÍ"
        lines.append(
            f"  {i}. {a['planet1_sk']} {a['aspect_sk']} {a['planet2_sk']} "
            f"(orb {a['orb']}° — {orb_strength})"
        )

    lines.append("")
    lines.append(
        "Analyzuj KAŽDÝ aspekt z vyššie uvedeného zoznamu. "
        "Zachovaj poradie. Pre každý použi formát ASPEKT: ... podľa inštrukcií."
    )
    return "\n".join(lines)


def _parse_aspects_response(text, chart_aspects):
    """Parsuje odpoveď s analýzou aspektov."""
    results = []
    current_header = None
    current_lines = []

    def flush():
        if current_header and current_lines:
            content = ' '.join(line for line in current_lines if line).strip()
            if content:
                results.append({
                    'header': current_header,
                    'text': content,
                })

    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue

        upper = stripped.upper()
        # Detect ASPEKT: header
        if upper.startswith('ASPEKT:') or upper.startswith('**ASPEKT:'):
            flush()
            # Extract the header text after "ASPEKT:"
            header = stripped
            # Clean up markdown bold markers
            header = header.replace('**', '')
            # Remove "ASPEKT: " prefix
            if ':' in header:
                parts = header.split(':', 1)
                if len(parts) > 1:
                    after = parts[1].strip().rstrip(':')
                    current_header = after if after else parts[0]
                else:
                    current_header = header
            else:
                current_header = header
            current_lines = []
        elif current_header is not None:
            # Clean markdown formatting
            clean = stripped.replace('**', '').strip()
            if clean:
                current_lines.append(clean)
        else:
            # No header yet — check if this line IS the aspect header (without ASPEKT: prefix)
            # Some models skip the prefix
            for a in chart_aspects:
                check = f"{a['planet1_sk']} {a['aspect_sk']} {a['planet2_sk']}"
                if check.lower() in stripped.lower().replace('**', ''):
                    flush()
                    current_header = stripped.replace('**', '').rstrip(':').strip()
                    current_lines = []
                    break

    flush()

    # Match parsed results with chart aspects for consistent ordering
    matched = []
    used = set()
    for a in chart_aspects:
        key = f"{a['planet1_sk']} {a['aspect_sk']} {a['planet2_sk']}"
        best = None
        best_idx = -1
        for i, r in enumerate(results):
            if i in used:
                continue
            # Fuzzy match: check if both planet names appear in header
            h_lower = r['header'].lower()
            if a['planet1_sk'].lower() in h_lower and a['planet2_sk'].lower() in h_lower:
                best = r
                best_idx = i
                break
        if best and best_idx >= 0:
            used.add(best_idx)
            matched.append({
                'header': key,
                'aspect_type': a['aspect'],
                'orb': a['orb'],
                'text': best['text'],
                'planet1': a['planet1_sk'],
                'planet2': a['planet2_sk'],
                'aspect_sk': a['aspect_sk'],
            })
        else:
            # Fallback: use the aspect name but no AI text
            matched.append({
                'header': key,
                'aspect_type': a['aspect'],
                'orb': a['orb'],
                'text': '',
                'planet1': a['planet1_sk'],
                'planet2': a['planet2_sk'],
                'aspect_sk': a['aspect_sk'],
            })

    # Add any remaining unmatched results
    for i, r in enumerate(results):
        if i not in used:
            matched.append({
                'header': r['header'],
                'aspect_type': 'conjunction',
                'orb': 0,
                'text': r['text'],
                'planet1': '',
                'planet2': '',
                'aspect_sk': '',
            })

    return matched


def _fallback_aspects_analysis(chart):
    """Deterministický fallback textov pre natálne aspekty."""
    aspects = chart.get('aspects') or []
    if not aspects:
        return [{
            'header': 'Bez výrazných aspektov',
            'aspect_type': 'conjunction',
            'orb': 0,
            'text': (
                'V horoskope neboli identifikované výrazné tesné aspekty. '
                'Pracuj preto hlavne s polohami planét v znameniach a domoch.'
            ),
            'planet1': '',
            'planet2': '',
            'aspect_sk': '',
        }]

    type_templates = {
        'conjunction': (
            'Konjunkcia zlučuje energie oboch planét do jedného dominantného motívu. '
            'Táto téma sa aktivuje spontánne a potrebuje vedomé smerovanie.'
        ),
        'sextile': (
            'Sextil prináša prirodzený talent, ktorý rastie cez vedomú aktivitu. '
            'Keď sa tejto téme venuješ pravidelne, výsledky bývajú stabilné.'
        ),
        'trine': (
            'Trigón ukazuje plynulý potenciál a ľahšie zvládanie tejto oblasti. '
            'Dôležité je nezostať len v komforte a talent aj prakticky rozvíjať.'
        ),
        'square': (
            'Kvadratúra vytvára vnútorné napätie, ktoré ťa tlačí do rastu. '
            'Kľúčom je disciplína, trpezlivosť a postupné nastavovanie hraníc.'
        ),
        'opposition': (
            'Opozícia ukazuje polaritu, ktorú potrebuješ vyvažovať medzi dvoma pólmi. '
            'Integrácia oboch strán dáva najzrelejšie výsledky.'
        ),
    }

    fallback = []
    for a in aspects:
        planet1 = a.get('planet1_sk', '')
        planet2 = a.get('planet2_sk', '')
        aspect_type = a.get('aspect', 'conjunction')
        orb = float(a.get('orb', 0) or 0)
        strength = 'tesný' if orb < 1 else ('silný' if orb < 3 else 'mierny')
        base = type_templates.get(aspect_type, type_templates['conjunction'])

        text = (
            f"{planet1} a {planet2} tvoria {strength} aspekt (orb {orb}°). "
            f"{base}"
        )
        fallback.append({
            'header': f"{planet1} {a.get('aspect_sk', '')} {planet2}".strip(),
            'aspect_type': aspect_type,
            'orb': orb,
            'text': text,
            'planet1': planet1,
            'planet2': planet2,
            'aspect_sk': a.get('aspect_sk', ''),
        })

    return fallback


# ═══════════════════════════════════════════
# Gemini AI denné hodnotenie
# ═══════════════════════════════════════════

GEMINI_SYSTEM = """Si senior astrológ so silnou expertízou v tranzitoch, planetárnych cykloch, aspektoch a praktickej interpretácii.

ÚLOHA:
- Na základe vstupných tranzitov priprav praktické denné astrologické hodnotenie.
- Píš po slovensky, konkrétne, bez ezoterického balastu a bez klišé.
- Integruj astrologickú logiku: typ aspektu, orb, intenzitu, povahu planét.

VÝSTUP:
- Vráť LEN validný JSON (žiadny markdown, žiadny text navyše).
- Povinná štruktúra:
{
  "rating": 1-10 integer,
  "energy": "2-4 vety",
  "focus": ["bod 1", "bod 2", "bod 3"],
  "avoid": ["bod 1", "bod 2", "bod 3"]
}
"""


def _build_ai_prompt(profile, target_date, active_transits):
    """Zostaví user prompt pre Gemini z aktívnych tranzitov."""
    lines = [
        f"Dátum: {target_date.strftime('%d.%m.%Y (%A)')}",
        f"Osoba: {profile.name}",
        f"Pohlavie profilu: {profile.get_gender_display()}",
        f"Jazykový pokyn: {_gender_addressing_instruction(profile)}",
        "",
        "Aktívne tranzity v tento deň:",
    ]
    for t in active_transits:
        effect_sk = {'positive': 'pozitívny', 'negative': 'negatívny', 'neutral': 'neutrálny'}.get(t['effect'], t['effect'])
        lines.append(
            f"- {t['title']} ({effect_sk}) | orb: {t.get('orb')}°/{t.get('orb_limit')}° | "
            f"intenzita: {int((t.get('intensity', 0) or 0)*100)}% | text: {t['text']}"
        )
    lines.append("")
    lines.append("Vytvor denné hodnotenie podľa pokynov a vráť len validný JSON.")
    return "\n".join(lines)


def _parse_ai_text_response(text):
    """Legacy parser pre textový fallback."""
    result = {
        'rating': 5,
        'energy': '',
        'focus': [],
        'avoid': [],
        'raw': text,
    }

    current_section = None
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        upper = line.upper()
        if upper.startswith('HODNOTENIE:'):
            try:
                val = line.split(':')[1].strip().split('/')[0].strip()
                result['rating'] = max(1, min(10, int(val)))
            except (ValueError, IndexError):
                pass
            current_section = None
        elif upper.startswith('ENERGIA DŇA:') or upper.startswith('ENERGIA DNA:'):
            current_section = 'energy'
            # Text môže byť na rovnakom riadku
            after = line.split(':', 1)[1].strip() if ':' in line else ''
            if after:
                result['energy'] += after + ' '
        elif upper.startswith('NA ČO SA SÚSTREDIŤ:') or upper.startswith('NA CO SA SUSTREDIT:'):
            current_section = 'focus'
        elif upper.startswith('ČOMU SA VYHNÚŤ:') or upper.startswith('COMU SA VYHNUT:'):
            current_section = 'avoid'
        elif line.startswith('- ') or line.startswith('• '):
            item = line[2:].strip()
            if current_section == 'focus':
                result['focus'].append(item)
            elif current_section == 'avoid':
                result['avoid'].append(item)
            elif current_section == 'energy':
                result['energy'] += item + ' '
        else:
            if current_section == 'energy':
                result['energy'] += line + ' '

    result['energy'] = result['energy'].strip()
    return result


def _parse_ai_response(payload):
    """Parsuje JSON payload z modelu do interného formátu."""
    if not isinstance(payload, dict):
        return _parse_ai_text_response(payload or '')

    result = {
        'rating': 5,
        'energy': '',
        'focus': [],
        'avoid': [],
        'raw': payload,
    }
    try:
        result['rating'] = max(1, min(10, int(payload.get('rating', 5))))
    except Exception:
        result['rating'] = 5

    energy = payload.get('energy', '')
    result['energy'] = (energy or '').strip()
    result['focus'] = [str(x).strip() for x in (payload.get('focus') or []) if str(x).strip()][:3]
    result['avoid'] = [str(x).strip() for x in (payload.get('avoid') or []) if str(x).strip()][:3]
    return result


def _fallback_ai_day_report(active_transits):
    """Fallback, ak AI vráti prázdnu alebo neparsovateľnú odpoveď."""
    positives = sum(1 for t in active_transits if t.get('effect') == 'positive')
    negatives = sum(1 for t in active_transits if t.get('effect') == 'negative')
    rating = 6 + min(2, positives) - min(2, negatives)
    rating = max(3, min(9, rating))

    focus = []
    avoid = []
    for t in active_transits[:6]:
        title = t.get('title', 'Tranzit')
        if t.get('effect') == 'negative':
            avoid.append(f"Neurob unáhlené rozhodnutia v téme: {title}.")
        else:
            focus.append(f"Využi momentum v téme: {title}.")

    if not focus:
        focus = [
            'Drž sa jasného plánu dňa.',
            'Komunikuj priamo a pokojne.',
            'Dôležité úlohy rieš v prvom bloku dňa.',
        ]
    if not avoid:
        avoid = [
            'Nerob impulzívne reakcie pod tlakom.',
            'Nevstupuj do zbytočných konfliktov.',
            'Neignoruj potrebu oddychu.',
        ]

    return {
        'rating': rating,
        'energy': (
            'Energia dňa je dynamická a premenlivá. '
            'Najlepšie funguje vedomé tempo, jasné priority a vecná komunikácia.'
        ),
        'focus': focus[:3],
        'avoid': avoid[:3],
        'raw': '',
    }


@login_required(login_url='transits:login')
@require_http_methods(["POST"])
def ai_day_report(request):
    """API endpoint - Gemini AI hodnotenie dňa."""
    if not _has_gemini_key():
        return JsonResponse({
            'error': 'Gemini API kľúč nie je nakonfigurovaný. Nastav ho v admin sekcii Gemini konfigurácia alebo v .env.'
        }, status=500)

    try:
        body = json.loads(request.body)
        profile_id = body.get('profile_id')
        day_offset = body.get('day_offset', 0)
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'error': 'Neplatný request.'}, status=400)

    profile = get_object_or_404(NatalProfile, pk=profile_id)

    # Vypočítame tranzity
    all_transits = _compute_transits_for_profile(profile, request=request)

    # Vyfiltrujeme aktívne tranzity pre poludnie daného dňa
    target_date = date.today() + timedelta(days=day_offset)
    target_noon = datetime.combine(target_date, time(12, 0))

    active = []
    for t in all_transits:
        try:
            ts = datetime.fromisoformat(t['start_date_iso']).timestamp() * 1000
            te = datetime.fromisoformat(t['end_date_iso']).timestamp() * 1000
            noon_ms = target_noon.timestamp() * 1000
            if ts <= noon_ms and te >= noon_ms:
                active.append(t)
        except (ValueError, KeyError):
            continue

    if not active:
        return JsonResponse({
            'rating': 5,
            'energy': 'Pre tento deň nie sú dostupné žiadne výrazné tranzity.',
            'focus': ['Bežný deň bez silných planetárnych vplyvov.'],
            'avoid': ['Žiadne špecifické obmedzenia.'],
        })

    # Zostavíme prompt
    user_prompt = _build_ai_prompt(profile, target_date, active)

    # Zavoláme Gemini
    try:
        ai_text = generate_gemini_text(
            model_name=get_gemini_model(),
            contents=user_prompt,
            system_instruction=GEMINI_SYSTEM,
            temperature=0.55,
            max_output_tokens=700,
            response_mime_type='application/json',
            retries=2,
            timeout_seconds=50,
        )
        payload = parse_json_payload(ai_text)
        parsed = _parse_ai_response(payload if payload is not None else ai_text)
        if not parsed.get('energy') or len(parsed.get('focus', [])) < 2 or len(parsed.get('avoid', [])) < 2:
            parsed = _fallback_ai_day_report(active)
        return JsonResponse(parsed)

    except GeminiLimitExceededError:
        return JsonResponse({
            'error': 'Denný limit AI volaní bol prekročený. Skúste to neskôr.',
            'limit_exceeded': True,
        }, status=503)
    except Exception as e:
        logger.error(f"Gemini API error v AI hodnotení dňa, používam fallback: {e}")
        parsed = _fallback_ai_day_report(active)
        parsed['warning'] = 'AI odpoveď nebola dostupná, zobrazený je fallback.'
        return JsonResponse(parsed)
