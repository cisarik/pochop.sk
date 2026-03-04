import json
import logging
import threading
import ipaddress
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from datetime import date, time, datetime, timedelta
from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.utils import OperationalError, ProgrammingError
from django.db.models import F, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
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
from django.utils import timezone
from .models import (
    AIModelOption,
    AIDayReportCache,
    AIDayReportDailyStat,
    AINatalAnalysisCache,
    GeminiConfig,
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
from .moment_service import (
    MOMENT_DEFAULT_LOCATION_KEY,
    MOMENT_TZ,
    build_moment_location_payload,
    enrich_moment_aspects_with_text,
    get_or_generate_moment_report,
)
from .transit_data import TRANSIT_DATA
from .gemini_utils import (
    GeminiLimitExceededError,
    generate_ai_text,
    generate_gemini_text,
    get_active_model_context,
    get_gemini_model,
    has_ai_key,
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
from .access import user_can_switch_ai_model, user_has_pro_account
from .ai_request_context import clear_ai_request_context, set_ai_request_context
from .credits import AICreditLimitExceededError
from .services.geocoding import geocode_forward, geocode_reverse
from .services.ip_geo import ip_to_location
from .services.city_lookup import find_nearest_slovak_city

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
    # Legacy helper name; now validates key for currently active model/provider.
    return has_ai_key()


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
    active_model_ctx = get_active_model_context()
    active_model_ref = _normalize_ai_day_model_ref(active_model_ctx)
    moment_report = (
        MomentReport.objects.filter(
            report_date=today,
            model_ref=active_model_ref,
            location_key=MOMENT_DEFAULT_LOCATION_KEY,
        ).first()
        or MomentReport.objects.filter(
            model_ref=active_model_ref,
            location_key=MOMENT_DEFAULT_LOCATION_KEY,
        ).order_by('-report_date').first()
        or MomentReport.objects.order_by('-report_date').first()
    )

    context = {}
    if moment_report:
        landing_aspects = enrich_moment_aspects_with_text(moment_report.aspects_json)
        context = {
            'landing_moment_report': moment_report,
            'landing_moment_planets_json': json.dumps(moment_report.planets_json, ensure_ascii=False),
            'landing_moment_aspects_json': json.dumps(landing_aspects, ensure_ascii=False),
        }
    return render(request, 'transits/index.html', context)


def moment_overview(request):
    """Verejná stránka s denným astrologickým rozborom okamihu."""
    city_param = request.GET.get('city', '')
    country_param = request.GET.get('country', '')
    lat_param = request.GET.get('lat')
    lon_param = request.GET.get('lon')

    if (not str(city_param or '').strip()) and lat_param is not None and lon_param is not None:
        nearest_city = find_nearest_slovak_city(lat_param, lon_param)
        if nearest_city:
            city_param = nearest_city.get('name') or city_param
            if not str(country_param or '').strip():
                country_param = 'Slovensko'

    report_location = build_moment_location_payload(
        lat=lat_param,
        lon=lon_param,
        city=city_param,
        country=country_param,
        name=request.GET.get('location', ''),
        timezone_name=MOMENT_TZ,
    )
    report = get_or_generate_moment_report(location=report_location)
    active_model_ctx = getattr(report, '_active_model_ctx', None) or get_active_model_context()
    report_aspects = enrich_moment_aspects_with_text(report.aspects_json)
    location_payload = report.ai_report_json.get('location') if isinstance(report.ai_report_json, dict) else {}
    location_name = str((location_payload or {}).get('name') or getattr(report, 'location_name', '') or '').strip()
    location_lat = (location_payload or {}).get('lat')
    location_lon = (location_payload or {}).get('lon')
    if location_lat is None:
        location_lat = getattr(report, 'location_lat', None)
    if location_lon is None:
        location_lon = getattr(report, 'location_lon', None)
    return render(request, 'transits/moment.html', {
        'report_date': report.report_date,
        'moment_planets_json': json.dumps(report.planets_json, ensure_ascii=False),
        'moment_aspects_json': json.dumps(report_aspects, ensure_ascii=False),
        'moment_ai_json': json.dumps(report.ai_report_json, ensure_ascii=False),
        'moment_generated_at': report.updated_at,
        'moment_ai_model_badge': active_model_ctx.get('badge', ''),
        'moment_cache_hit': bool(getattr(report, '_cache_hit', False)),
        'moment_location_name': location_name,
        'moment_location_lat': location_lat,
        'moment_location_lon': location_lon,
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
        _set_analysis_error(profile_id, 'API kľúč pre aktívny AI model nie je nakonfigurovaný v .env.')
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
        set_ai_request_context(
            user_id=getattr(profile, 'user_id', None),
            path='/internal/natal-analysis/background',
            method='WORKER',
        )
        try:
            success = _generate_and_save_analyses(profile)
        finally:
            clear_ai_request_context()
        if success:
            _set_analysis_error(profile_id, None)
        elif not _has_gemini_key():
            _set_analysis_error(profile_id, 'API kľúč pre aktívny AI model nie je nakonfigurovaný v .env.')
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


def loginpro_view(request):
    """Informačná stránka pre Pro účet."""
    return render(request, 'transits/loginpro.html')


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
# Location API
# ═══════════════════════════════════════════

_LOCATION_MAX_PART_LEN = 120


def _parse_json_body(request):
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return None, 'Neplatný JSON payload.'
    if not isinstance(data, dict):
        return None, 'JSON payload musí byť objekt.'
    return data, ''


def _normalize_location_part(value, *, field):
    cleaned = ' '.join(str(value or '').strip().split())
    if not cleaned:
        return '', f'Pole `{field}` je povinné.'
    if len(cleaned) > _LOCATION_MAX_PART_LEN:
        return '', f'Pole `{field}` je príliš dlhé.'
    return cleaned, ''


def _extract_client_ip(request):
    candidates = []

    # CDN/proxy headers (Cloudflare, Akamai, etc.)
    for header_name in ('HTTP_CF_CONNECTING_IP', 'HTTP_TRUE_CLIENT_IP'):
        header_val = str(request.META.get(header_name, '') or '').strip()
        if header_val:
            candidates.append(header_val)

    x_forwarded_for = str(request.META.get('HTTP_X_FORWARDED_FOR', '') or '').strip()
    if x_forwarded_for:
        candidates.extend([part.strip() for part in x_forwarded_for.split(',') if part.strip()])

    x_real_ip = str(request.META.get('HTTP_X_REAL_IP', '') or '').strip()
    if x_real_ip:
        candidates.append(x_real_ip)

    remote_addr = str(request.META.get('REMOTE_ADDR', '') or '').strip()
    if remote_addr:
        candidates.append(remote_addr)

    valid_ips = []
    public_ips = []
    for candidate in candidates:
        try:
            parsed = ipaddress.ip_address(candidate)
        except ValueError:
            continue

        normalized = str(parsed)
        valid_ips.append(normalized)
        is_public = not (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_multicast
            or parsed.is_unspecified
        )
        if is_public:
            public_ips.append(normalized)

    if public_ips:
        return public_ips[0]
    if valid_ips:
        return valid_ips[0]
    return ''


def _normalize_country_token(value):
    return ' '.join(str(value or '').strip().lower().split())


def _is_slovakia_country(value):
    token = _normalize_country_token(value)
    return token in {
        'slovensko',
        'slovakia',
        'slovak republic',
        'slovak republic (slovakia)',
        'sk',
        'svk',
    }


def _looks_like_slovak_coordinates(lat, lon):
    try:
        lat_val = float(lat)
        lon_val = float(lon)
    except (TypeError, ValueError):
        return False
    return 47.6 <= lat_val <= 49.7 and 16.7 <= lon_val <= 22.7


@require_http_methods(["POST"])
def api_location_reverse(request):
    body, err = _parse_json_body(request)
    if err:
        return JsonResponse({'error': err}, status=400)

    try:
        lat = float(body.get('lat'))
        lon = float(body.get('lon'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'lat/lon musia byť čísla.'}, status=400)

    if not (-90.0 <= lat <= 90.0):
        return JsonResponse({'error': 'lat je mimo rozsah -90..90.'}, status=400)
    if not (-180.0 <= lon <= 180.0):
        return JsonResponse({'error': 'lon je mimo rozsah -180..180.'}, status=400)

    payload = geocode_reverse(lat, lon)
    if not payload:
        return JsonResponse({'error': 'Lokalitu sa nepodarilo určiť.'}, status=404)

    return JsonResponse({
        'country': payload.get('country') or '',
        'city': payload.get('city') or '',
        'region': payload.get('region') or '',
        'postcode': payload.get('postcode') or '',
    })


@require_http_methods(["POST"])
def api_location_forward(request):
    body, err = _parse_json_body(request)
    if err:
        return JsonResponse({'error': err}, status=400)

    country, country_err = _normalize_location_part(body.get('country'), field='country')
    if country_err:
        return JsonResponse({'error': country_err}, status=400)

    city, city_err = _normalize_location_part(body.get('city'), field='city')
    if city_err:
        return JsonResponse({'error': city_err}, status=400)

    region_raw = body.get('region')
    region = ' '.join(str(region_raw or '').strip().split())
    if len(region) > _LOCATION_MAX_PART_LEN:
        return JsonResponse({'error': 'Pole `region` je príliš dlhé.'}, status=400)

    payload = geocode_forward(country=country, city=city, region=region or None)
    if not payload:
        return JsonResponse({'error': 'Súradnice sa nepodarilo nájsť.'}, status=404)

    return JsonResponse({
        'lat': payload.get('lat'),
        'lon': payload.get('lon'),
        'country': payload.get('country') or country,
        'city': payload.get('city') or city,
        'region': payload.get('region') or region,
    })


@require_http_methods(["GET"])
def api_location_from_ip(request):
    client_ip = _extract_client_ip(request)
    if not client_ip:
        return HttpResponse(status=204)

    payload = ip_to_location(client_ip)
    if not payload:
        return HttpResponse(status=204)

    country = payload.get('country') or ''
    city = payload.get('city') or ''
    region = payload.get('region') or ''
    lat = payload.get('lat')
    lon = payload.get('lon')

    if lat is not None and lon is not None and (
        _is_slovakia_country(country) or _looks_like_slovak_coordinates(lat, lon) or not str(country).strip()
    ):
        nearest_city = find_nearest_slovak_city(lat, lon)
        if nearest_city:
            # Pre Slovensko berieme nearest city z GPS ako source of truth.
            city = nearest_city.get('name') or city
            if not region:
                region = nearest_city.get('district') or ''
            if not country:
                country = 'Slovensko'

    return JsonResponse({
        'country': country,
        'city': city,
        'region': region,
        'lat': lat,
        'lon': lon,
    })


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
    compare_models = _get_enabled_compare_models(user=request.user)
    compare_refs = [item['model_ref'] for item in compare_models]
    active_ref = _normalize_ai_day_model_ref(get_active_model_context())
    compare_model_limit = _get_compare_models_limit()
    default_compare_refs = []
    if compare_models:
        default_compare_refs = [active_ref] if active_ref in compare_refs else [compare_refs[0]]

    return render(request, 'transits/timeline.html', {
        'profile': profile,
        'transits': json.dumps(transits_data, ensure_ascii=False),
        'transits_list': transits_data,
        'profile_birth_date': birth_labels['birth_date'],
        'profile_birth_time': birth_labels['birth_time'],
        'profile_birth_place': birth_labels['birth_place'],
        'compare_ai_models': compare_models,
        'compare_ai_models_json': json.dumps(compare_models, ensure_ascii=False),
        'default_compare_model_refs_json': json.dumps(default_compare_refs, ensure_ascii=False),
        'compare_model_limit': compare_model_limit,
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


def _get_natal_cache_expiry():
    ttl_days = int(getattr(settings, 'AI_NATAL_CACHE_TTL_DAYS', 120) or 120)
    ttl_days = max(1, ttl_days)
    return timezone.now() + timedelta(days=ttl_days)


def _load_cached_natal_analysis(profile, model_ref):
    try:
        now = timezone.now()
        item = (
            AINatalAnalysisCache.objects
            .filter(
                profile=profile,
                model_ref=model_ref,
                expires_at__gt=now,
            )
            .only(
                'id',
                'analysis_json',
                'aspects_json',
                'generated_at',
                'profile_updated_at',
            )
            .first()
        )
        if not item:
            return None

        profile_updated_at = getattr(profile, 'updated_at', None)
        if item.profile_updated_at and profile_updated_at and item.profile_updated_at < profile_updated_at:
            return None

        AINatalAnalysisCache.objects.filter(pk=item.pk).update(
            hits=F('hits') + 1,
            last_served_at=now,
            updated_at=now,
        )
        return item
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("Natal compare cache read unavailable (%s): %s", model_ref, exc)
        return None


def _store_natal_analysis_cache(profile, model_ref, analysis_json, aspects_json):
    now = timezone.now()
    try:
        AINatalAnalysisCache.objects.update_or_create(
            profile=profile,
            model_ref=model_ref,
            defaults={
                'analysis_json': analysis_json if isinstance(analysis_json, list) else [],
                'aspects_json': aspects_json if isinstance(aspects_json, list) else [],
                'profile_updated_at': getattr(profile, 'updated_at', None),
                'hits': 0,
                'generated_at': now,
                'last_served_at': now,
                'expires_at': _get_natal_cache_expiry(),
            },
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("Natal compare cache write unavailable (%s): %s", model_ref, exc)
    return now


def _generate_natal_analyses_payload(profile, model_name=None, request=None):
    """Vygeneruje payload natálnej + aspektovej analýzy bez prepisu globálnych polí."""
    if not has_ai_key(model_name=model_name):
        logger.warning("AI API kľúč nie je nakonfigurovaný, preskakujem natálne analýzy.")
        return None

    chart = profile.natal_chart_json
    birth = None
    updated_fields = []

    if not chart:
        birth = _get_profile_birth_data(profile, request=request)
        if not birth:
            logger.error(
                "Profil %s nemá chart ani dešifrovateľné birth dáta, analýzu nemožno zregenerovať.",
                profile.pk,
            )
            return None
        chart = calculate_natal_chart(
            birth['birth_date'],
            birth['birth_time'],
            birth['birth_lat'],
            birth['birth_lon'],
            birth.get('timezone') or profile.timezone,
        )
        profile.natal_chart_json = chart
        updated_fields.append('natal_chart_json')

    if not profile.natal_positions_json:
        if birth is None:
            birth = _get_profile_birth_data(profile, request=request)
        if birth:
            profile.natal_positions_json = calculate_natal_positions(
                birth['birth_date'],
                birth['birth_time'],
                birth['birth_lat'],
                birth['birth_lon'],
                birth.get('timezone') or profile.timezone,
            )
            updated_fields.append('natal_positions_json')

    if updated_fields:
        try:
            profile.save(update_fields=updated_fields + ['updated_at'])
        except Exception as exc:
            logger.error("Uloženie natal chart/positions zlyhalo pre %s: %s", profile.name, exc)
            return None

    active_model = get_gemini_model(model_name)

    # Predvyplníme deterministic fallbacky, aby UI nezostalo bez textu.
    parsed_natal = _fallback_natal_sections(profile, chart)
    parsed_aspects = _fallback_aspects_analysis(chart)
    fallback_used = False
    warnings = []

    # 1. Natálna analýza
    try:
        natal_prompt = _build_natal_prompt(profile, chart)
        natal_text = generate_gemini_text(
            model_name=active_model,
            contents=natal_prompt,
            system_instruction=NATAL_SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=2200,
            cache_ttl_seconds=60 * 60 * 24 * 30,
            retries=2,
            timeout_seconds=60,
        )
        ai_natal = _parse_natal_response(natal_text)
        if _natal_payload_is_valid(ai_natal):
            parsed_natal = ai_natal
        else:
            # Poisoned prompt cache guard: retry once without cache before final fallback.
            retry_text = generate_gemini_text(
                model_name=active_model,
                contents=natal_prompt,
                system_instruction=NATAL_SYSTEM_PROMPT,
                temperature=0.55,
                max_output_tokens=2200,
                cache_ttl_seconds=0,
                retries=1,
                timeout_seconds=60,
            )
            retry_natal = _parse_natal_response(retry_text)
            if _natal_payload_is_valid(retry_natal):
                parsed_natal = retry_natal
                warnings.append('Natálna analýza bola vygenerovaná na druhý pokus (refresh bez cache).')
            else:
                fallback_used = True
                warnings.append('Natálna analýza mala nízku kvalitu, použitý fallback.')
                logger.warning(
                    "Natálna analýza pre %s mala slabú kvalitu aj po retry bez cache, ponechávam fallback.",
                    profile.name,
                )
    except GeminiLimitExceededError:
        raise
    except AICreditLimitExceededError:
        raise
    except Exception as exc:
        logger.error("Natálna analýza AI zlyhala pre %s: %s", profile.name, exc)
        fallback_used = True
        warnings.append('Natálna analýza AI zlyhala, použitý fallback.')

    # 2. Analýza aspektov
    try:
        aspects_prompt = _build_aspects_prompt(profile, chart)
        aspects_text = generate_gemini_text(
            model_name=active_model,
            contents=aspects_prompt,
            system_instruction=ASPECTS_SYSTEM_PROMPT,
            temperature=0.65,
            max_output_tokens=3200,
            cache_ttl_seconds=60 * 60 * 24 * 30,
            retries=2,
            timeout_seconds=70,
        )
        ai_aspects = _parse_aspects_response(aspects_text, chart['aspects'])
        if any((a.get('text') or '').strip() for a in ai_aspects):
            parsed_aspects = ai_aspects
        else:
            retry_text = generate_gemini_text(
                model_name=active_model,
                contents=aspects_prompt,
                system_instruction=ASPECTS_SYSTEM_PROMPT,
                temperature=0.5,
                max_output_tokens=3200,
                cache_ttl_seconds=0,
                retries=1,
                timeout_seconds=70,
            )
            retry_aspects = _parse_aspects_response(retry_text, chart['aspects'])
            if any((a.get('text') or '').strip() for a in retry_aspects):
                parsed_aspects = retry_aspects
                warnings.append('Aspektová analýza bola vygenerovaná na druhý pokus (refresh bez cache).')
            else:
                fallback_used = True
                warnings.append('Aspektová analýza bola prázdna, použitý fallback.')
                logger.warning(
                    "Aspektová analýza pre %s je prázdna aj po retry bez cache, ponechávam fallback.",
                    profile.name,
                )
    except GeminiLimitExceededError:
        raise
    except AICreditLimitExceededError:
        raise
    except Exception as exc:
        logger.error("Analýza aspektov AI zlyhala pre %s: %s", profile.name, exc)
        fallback_used = True
        warnings.append('Aspektová analýza AI zlyhala, použitý fallback.')

    model_ctx = get_active_model_context(model_name=model_name or active_model)
    return {
        'analysis_json': parsed_natal,
        'aspects_json': parsed_aspects,
        'model_ref': _normalize_ai_day_model_ref(model_ctx),
        'ai_model_ctx': model_ctx,
        'fallback_used': bool(fallback_used),
        'warning': ' '.join(warnings).strip(),
    }


def _generate_and_save_analyses(profile, model_name=None):
    """
    Vygeneruje natálnu analýzu aj analýzu aspektov cez Gemini
    a uloží výsledky do profilu. Volá sa raz pri registrácii.
    """
    try:
        payload = _generate_natal_analyses_payload(profile, model_name=model_name, request=None)
    except GeminiLimitExceededError:
        logger.warning("Denný limit AI prekročený pri natálnej analýze (%s).", profile.name)
        return False
    except AICreditLimitExceededError:
        logger.warning("Nedostatok kreditov pri natálnej analýze (%s).", profile.name)
        return False
    except Exception as exc:
        logger.error("Generovanie natálnej analýzy zlyhalo pre %s: %s", profile.name, exc)
        return False

    if not payload:
        return False

    profile.natal_analysis_json = payload['analysis_json']
    profile.natal_aspects_json = payload['aspects_json']

    try:
        profile.save(update_fields=['natal_analysis_json', 'natal_aspects_json', 'updated_at'])
    except Exception as exc:
        logger.error("Uloženie analýz zlyhalo pre %s: %s", profile.name, exc)
        return False

    try:
        _store_natal_analysis_cache(
            profile,
            payload['model_ref'],
            payload['analysis_json'],
            payload['aspects_json'],
        )
    except Exception as exc:
        logger.warning("Uloženie natal cache zlyhalo pre %s: %s", profile.name, exc)

    if profile.has_analysis:
        logger.info(f"Analýzy vygenerované a uložené pre {profile.name}")
        return True
    logger.warning(f"Analýza pre {profile.name} je neúplná, vyžaduje ďalší pokus.")
    return False


def _invalidate_all_natal_analyses():
    """
    Označí všetky uložené natálne analýzy na lazy refresh.
    Tokeny sa minú až keď konkrétny používateľ otvorí analýzu.
    """
    return NatalProfile.objects.filter(
        Q(natal_analysis_json__isnull=False) | Q(natal_aspects_json__isnull=False)
    ).update(
        natal_analysis_json=None,
        natal_aspects_json=None,
        updated_at=timezone.now(),
    )


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
    compare_models = _get_enabled_compare_models(user=request.user)
    compare_refs = [item['model_ref'] for item in compare_models]
    active_ref = _normalize_ai_day_model_ref(get_active_model_context())
    compare_model_limit = _get_compare_models_limit()
    default_compare_refs = []
    if compare_models:
        default_compare_refs = [active_ref] if active_ref in compare_refs else [compare_refs[0]]

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
        'compare_ai_models': compare_models,
        'compare_ai_models_json': json.dumps(compare_models, ensure_ascii=False),
        'default_compare_model_refs_json': json.dumps(default_compare_refs, ensure_ascii=False),
        'compare_model_limit': compare_model_limit,
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


def _build_natal_compare_result(
    *,
    analysis_sections,
    aspects_data,
    active_model_ctx,
    generated_at,
    cache_hit,
    ok=True,
    error='',
    limit_exceeded=False,
    fallback_used=False,
    warning='',
):
    generated_iso = timezone.localtime(generated_at).isoformat() if generated_at else ''
    return {
        'ok': bool(ok),
        'analysis_sections': analysis_sections if isinstance(analysis_sections, list) else [],
        'aspects_data': aspects_data if isinstance(aspects_data, list) else [],
        'ai_model_provider': active_model_ctx.get('provider', ''),
        'ai_model': active_model_ctx.get('model', ''),
        'ai_model_badge': active_model_ctx.get('badge', 'AI'),
        'ai_model_ref': _normalize_ai_day_model_ref(active_model_ctx),
        'generated_at': generated_iso,
        'generated_at_display': _format_ai_generated_at(generated_at),
        'cache_hit': bool(cache_hit),
        'error': error,
        'limit_exceeded': bool(limit_exceeded),
        'fallback_used': bool(fallback_used),
        'warning': str(warning or '').strip(),
    }


def _build_natal_compare_error_result(model_ref, message, *, status=503, limit_exceeded=False):
    active_model_ctx = get_active_model_context(model_name=model_ref)
    result = _build_natal_compare_result(
        analysis_sections=[],
        aspects_data=[],
        active_model_ctx=active_model_ctx,
        generated_at=None,
        cache_hit=False,
        ok=False,
        error=message,
        limit_exceeded=limit_exceeded,
    )
    err = {
        'model_ref': result.get('ai_model_ref'),
        'ai_model_badge': result.get('ai_model_badge'),
        'error': message,
        'limit_exceeded': bool(limit_exceeded),
        'status': int(status or 500),
    }
    return result, err


def _get_or_generate_natal_compare_for_model(profile, model_ref, *, request=None, key_error_status=503):
    active_model_ctx = get_active_model_context(model_name=model_ref)
    normalized_ref = _normalize_ai_day_model_ref(active_model_ctx)

    cache_row = _load_cached_natal_analysis(profile, normalized_ref)
    if cache_row:
        return _build_natal_compare_result(
            analysis_sections=cache_row.analysis_json,
            aspects_data=cache_row.aspects_json,
            active_model_ctx=active_model_ctx,
            generated_at=cache_row.generated_at,
            cache_hit=True,
            ok=True,
            fallback_used=False,
            warning='',
        ), None

    if not has_ai_key(model_name=model_ref):
        return _build_natal_compare_error_result(
            model_ref,
            'API kľúč pre zvolený AI model nie je nakonfigurovaný v .env.',
            status=key_error_status,
        )

    try:
        payload = _generate_natal_analyses_payload(profile, model_name=model_ref, request=request)
        if not payload:
            return _build_natal_compare_error_result(
                model_ref,
                'Nepodarilo sa vygenerovať natálnu analýzu pre zvolený model.',
                status=500,
            )
    except GeminiLimitExceededError:
        return _build_natal_compare_error_result(
            model_ref,
            'Denný limit AI volaní bol prekročený. Skúste to neskôr.',
            status=503,
            limit_exceeded=True,
        )
    except AICreditLimitExceededError:
        return _build_natal_compare_error_result(
            model_ref,
            'Nedostatok AI kreditov. Dobite kredity a skús to znovu.',
            status=402,
        )
    except Exception as exc:
        logger.error("Natálna compare analýza zlyhala pre model %s: %s", model_ref, exc)
        return _build_natal_compare_error_result(
            model_ref,
            'Generovanie natálnej analýzy zlyhalo.',
            status=500,
        )

    generated_at = _store_natal_analysis_cache(
        profile,
        normalized_ref,
        payload['analysis_json'],
        payload['aspects_json'],
    )
    return _build_natal_compare_result(
        analysis_sections=payload['analysis_json'],
        aspects_data=payload['aspects_json'],
        active_model_ctx=active_model_ctx,
        generated_at=generated_at,
        cache_hit=False,
        ok=True,
        fallback_used=bool(payload.get('fallback_used')),
        warning=payload.get('warning') or '',
    ), None


@login_required(login_url='transits:login')
@require_http_methods(["POST"])
def api_natal_analysis_compare(request):
    """Lazy compare endpoint pre natálne analýzy medzi vybranými modelmi."""
    try:
        body = json.loads(request.body or '{}')
        profile_id = body.get('profile_id')
        model_refs_raw = body.get('model_refs')
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Neplatný request.'}, status=400)

    model_refs, model_refs_error = _validate_compare_model_refs(
        model_refs_raw,
        max_items=_get_compare_models_limit(),
        user=request.user,
    )
    if model_refs_error:
        return JsonResponse({'error': model_refs_error}, status=400)

    profile = get_object_or_404(NatalProfile, pk=profile_id)
    if not request.user.is_staff and profile.user_id != request.user.pk:
        return JsonResponse({'error': 'Nemáš prístup k tomuto profilu.'}, status=403)

    results = []
    errors = []
    for model_ref in model_refs:
        item, err = _get_or_generate_natal_compare_for_model(
            profile,
            model_ref,
            request=request,
            key_error_status=503,
        )
        results.append(item)
        if err:
            errors.append({
                'model_ref': err.get('model_ref'),
                'ai_model_badge': err.get('ai_model_badge'),
                'error': err.get('error'),
                'limit_exceeded': bool(err.get('limit_exceeded')),
                'status': int(err.get('status') or 500),
            })

    success_count = sum(1 for item in results if item.get('ok'))
    status_code = 200
    if success_count == 0 and errors:
        if any((err.get('status') or 0) >= 500 for err in errors):
            status_code = 503
        elif any((err.get('status') or 0) == 402 for err in errors):
            status_code = 402
        else:
            status_code = 400

    return JsonResponse({
        'profile_id': profile.pk,
        'requested_model_refs': model_refs,
        'results': results,
        'errors': errors,
        'partial': bool(errors),
        'ok_models': success_count,
    }, status=status_code)


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
# AI denné hodnotenie
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


def _normalize_ai_day_model_ref(active_model_ctx):
    provider = str(active_model_ctx.get('provider') or '').strip().lower()
    model = str(active_model_ctx.get('model') or '').strip()
    if provider and model:
        return f"{provider}:{model}"
    return model or provider or 'ai:unknown'


def _get_ai_day_next_midnight():
    """Najbližšia lokálna polnoc (Europe/Bratislava podľa Django TIME_ZONE)."""
    now_local = timezone.localtime(timezone.now())
    return (now_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _format_ai_generated_at(dt_obj):
    if not dt_obj:
        return ''
    local_dt = timezone.localtime(dt_obj)
    return local_dt.strftime('%d.%m.%Y %H:%M')


def _record_ai_day_stats(
    model_ref,
    *,
    total_requests=0,
    cache_hits=0,
    generated_reports=0,
    fallback_reports=0,
    errors_count=0,
):
    deltas = {
        'total_requests': int(total_requests or 0),
        'cache_hits': int(cache_hits or 0),
        'generated_reports': int(generated_reports or 0),
        'fallback_reports': int(fallback_reports or 0),
        'errors_count': int(errors_count or 0),
    }
    if not any(deltas.values()):
        return

    try:
        stat_date = timezone.localdate()
        with transaction.atomic():
            stat, _ = AIDayReportDailyStat.objects.select_for_update().get_or_create(
                stat_date=stat_date,
                model_ref=model_ref,
                defaults={
                    'total_requests': 0,
                    'cache_hits': 0,
                    'generated_reports': 0,
                    'fallback_reports': 0,
                    'errors_count': 0,
                },
            )
            update_kwargs = {}
            for field, delta in deltas.items():
                if delta:
                    update_kwargs[field] = F(field) + delta
            if update_kwargs:
                update_kwargs['updated_at'] = timezone.now()
                AIDayReportDailyStat.objects.filter(pk=stat.pk).update(**update_kwargs)
    except Exception as exc:
        logger.warning("AI day stats update failed for %s: %s", model_ref, exc)


def _load_cached_ai_day_report(profile, target_date, model_ref):
    now = timezone.now()
    item = (
        AIDayReportCache.objects
        .filter(
            profile=profile,
            target_date=target_date,
            model_ref=model_ref,
            expires_at__gt=now,
        )
        .only('id', 'payload_json', 'generated_at', 'profile_updated_at', 'hits')
        .first()
    )
    if not item:
        return None

    profile_updated_at = getattr(profile, 'updated_at', None)
    if item.profile_updated_at and profile_updated_at and item.profile_updated_at < profile_updated_at:
        return None

    AIDayReportCache.objects.filter(pk=item.pk).update(
        hits=F('hits') + 1,
        last_served_at=now,
        updated_at=now,
    )
    return item


def _store_ai_day_report_cache(profile, target_date, model_ref, payload):
    now = timezone.now()
    expires_at = _get_ai_day_next_midnight()
    if expires_at <= now:
        expires_at = now + timedelta(minutes=5)
    payload_clean = payload if isinstance(payload, dict) else {}

    AIDayReportCache.objects.update_or_create(
        profile=profile,
        target_date=target_date,
        model_ref=model_ref,
        defaults={
            'payload_json': payload_clean,
            'profile_updated_at': getattr(profile, 'updated_at', None),
            'hits': 0,
            'generated_at': now,
            'last_served_at': now,
            'expires_at': expires_at,
        },
    )
    return now


def _build_ai_day_response_payload(payload, active_model_ctx, generated_at, cache_hit):
    payload_dict = payload if isinstance(payload, dict) else {}
    try:
        rating = max(1, min(10, int(payload_dict.get('rating', 5))))
    except Exception:
        rating = 5

    focus = [str(x).strip() for x in (payload_dict.get('focus') or []) if str(x).strip()][:3]
    avoid = [str(x).strip() for x in (payload_dict.get('avoid') or []) if str(x).strip()][:3]

    generated_iso = timezone.localtime(generated_at).isoformat() if generated_at else ''
    response = {
        'rating': rating,
        'energy': str(payload_dict.get('energy') or '').strip(),
        'focus': focus,
        'avoid': avoid,
        'ai_model_provider': active_model_ctx.get('provider', ''),
        'ai_model': active_model_ctx.get('model', ''),
        'ai_model_badge': active_model_ctx.get('badge', 'AI'),
        'ai_model_ref': _normalize_ai_day_model_ref(active_model_ctx),
        'generated_at': generated_iso,
        'generated_at_display': _format_ai_generated_at(generated_at),
        'cache_hit': bool(cache_hit),
    }
    if payload_dict.get('_fallback_used'):
        response['fallback_used'] = True
    warning_text = str(payload_dict.get('_warning') or '').strip()
    if warning_text:
        response['warning'] = warning_text
    return response


def _can_access_pro_models(user):
    if bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)):
        return True
    return user_has_pro_account(user)


def _get_compare_models_limit():
    default_limit = int(getattr(settings, 'AI_COMPARE_MAX_MODELS', 3) or 3)
    limit = default_limit
    try:
        cfg = GeminiConfig.objects.order_by('-updated_at').only('max_compare_models').first()
        if cfg and cfg.max_compare_models:
            limit = int(cfg.max_compare_models)
    except Exception:
        limit = default_limit
    return max(1, min(10, int(limit)))


def _get_enabled_compare_models(*, user=None):
    rows = []
    try:
        qs = AIModelOption.objects.filter(is_enabled=True, is_available=True)
        if not _can_access_pro_models(user):
            qs = qs.filter(is_pro_only=False)
        rows = list(qs.order_by('sort_order', 'label').values('label', 'model_ref'))
    except (OperationalError, ProgrammingError):
        try:
            qs = AIModelOption.objects.filter(is_enabled=True)
            rows = list(qs.order_by('sort_order', 'label').values('label', 'model_ref'))
        except Exception:
            rows = []
    except Exception:
        rows = []

    models = []
    for row in rows:
        model_ref = str(row.get('model_ref') or '').strip()
        if not model_ref:
            continue
        model_ctx = get_active_model_context(model_name=model_ref)
        models.append({
            'label': str(row.get('label') or model_ref).strip(),
            'model_ref': model_ref,
            'badge': model_ctx.get('badge', model_ref),
            'provider': model_ctx.get('provider', ''),
            'provider_label': model_ctx.get('provider_label', 'AI'),
        })
    return models


def _validate_compare_model_refs(model_refs, *, max_items=None, user=None):
    if max_items is None:
        max_items = _get_compare_models_limit()
    try:
        max_items = max(1, int(max_items))
    except Exception:
        max_items = 3

    if not isinstance(model_refs, list):
        return None, 'model_refs musí byť pole.'

    cleaned = []
    seen = set()
    for raw_ref in model_refs:
        ref = str(raw_ref or '').strip()
        if not ref:
            continue
        if ref in seen:
            return None, 'model_refs obsahuje duplicity.'
        seen.add(ref)
        cleaned.append(ref)

    if not cleaned:
        return None, 'Vyber aspoň jeden AI model.'
    if len(cleaned) > max_items:
        return None, f'Maximálne {max_items} modely.'

    allowed = {item['model_ref'] for item in _get_enabled_compare_models(user=user)}
    if not allowed:
        return None, 'Nie sú dostupné žiadne povolené AI modely.'

    invalid = [ref for ref in cleaned if ref not in allowed]
    if invalid:
        return None, f"Neplatné model_refs: {', '.join(invalid)}."
    return cleaned, ''


def _collect_ai_day_active_transits(profile, target_date, request=None):
    all_transits = _compute_transits_for_profile(profile, request=request)
    target_noon = datetime.combine(target_date, time(12, 0))
    noon_ms = target_noon.timestamp() * 1000
    active = []

    for t in all_transits:
        try:
            ts = datetime.fromisoformat(t['start_date_iso']).timestamp() * 1000
            te = datetime.fromisoformat(t['end_date_iso']).timestamp() * 1000
            if ts <= noon_ms and te >= noon_ms:
                active.append(t)
        except (ValueError, KeyError):
            continue
    return active


def _fallback_ai_day_empty_transits_payload():
    return {
        'rating': 5,
        'energy': 'Pre tento deň nie sú dostupné žiadne výrazné tranzity.',
        'focus': ['Bežný deň bez silných planetárnych vplyvov.'],
        'avoid': ['Žiadne špecifické obmedzenia.'],
    }


def _build_ai_day_error_result(model_ref, message, *, limit_exceeded=False, status=503):
    active_model_ctx = get_active_model_context(model_name=model_ref)
    normalized_ref = _normalize_ai_day_model_ref(active_model_ctx)
    result = {
        'ok': False,
        'rating': None,
        'energy': '',
        'focus': [],
        'avoid': [],
        'ai_model_provider': active_model_ctx.get('provider', ''),
        'ai_model': active_model_ctx.get('model', ''),
        'ai_model_badge': active_model_ctx.get('badge', 'AI'),
        'ai_model_ref': normalized_ref,
        'generated_at': '',
        'generated_at_display': '',
        'cache_hit': False,
        'error': message,
        'limit_exceeded': bool(limit_exceeded),
    }
    err = {
        'model_ref': normalized_ref,
        'ai_model_badge': active_model_ctx.get('badge', 'AI'),
        'error': message,
        'limit_exceeded': bool(limit_exceeded),
        'status': int(status or 500),
    }
    return result, err


def _generate_ai_day_payload_for_model(profile, target_date, active_transits, model_ref):
    if not active_transits:
        return _fallback_ai_day_empty_transits_payload(), True, False, ''

    user_prompt = _build_ai_prompt(profile, target_date, active_transits)
    fallback_used = False
    had_error = False
    warning = ''
    try:
        ai_text = generate_gemini_text(
            model_name=model_ref,
            contents=user_prompt,
            system_instruction=GEMINI_SYSTEM,
            temperature=0.55,
            max_output_tokens=700,
            response_mime_type='application/json',
            cache_ttl_seconds=max(300, int((_get_ai_day_next_midnight() - timezone.now()).total_seconds())),
            retries=2,
            timeout_seconds=50,
        )
        payload = parse_json_payload(ai_text)
        parsed = _parse_ai_response(payload if payload is not None else ai_text)
        if not parsed.get('energy') or len(parsed.get('focus', [])) < 2 or len(parsed.get('avoid', [])) < 2:
            parsed = _fallback_ai_day_report(active_transits)
            fallback_used = True
        return parsed, fallback_used, had_error, warning
    except GeminiLimitExceededError:
        raise
    except AICreditLimitExceededError:
        raise
    except Exception as exc:
        logger.error("AI API error v AI hodnotení dňa (%s), používam fallback: %s", model_ref, exc)
        parsed = _fallback_ai_day_report(active_transits)
        warning = 'AI odpoveď nebola dostupná, zobrazený je fallback.'
        had_error = True
        fallback_used = True
        return parsed, fallback_used, had_error, warning


def _get_or_generate_ai_day_report_for_model(
    profile,
    target_date,
    model_ref,
    *,
    request=None,
    active_transits=None,
    key_error_status=500,
):
    active_model_ctx = get_active_model_context(model_name=model_ref)
    normalized_ref = _normalize_ai_day_model_ref(active_model_ctx)

    cache_row = _load_cached_ai_day_report(profile, target_date, normalized_ref)
    if cache_row:
        _record_ai_day_stats(normalized_ref, total_requests=1, cache_hits=1)
        payload = _build_ai_day_response_payload(
            cache_row.payload_json,
            active_model_ctx=active_model_ctx,
            generated_at=cache_row.generated_at,
            cache_hit=True,
        )
        payload['ok'] = True
        return payload, None, active_transits

    if not has_ai_key(model_name=model_ref):
        _record_ai_day_stats(normalized_ref, total_requests=1, errors_count=1)
        result, err = _build_ai_day_error_result(
            model_ref,
            'API kľúč pre zvolený AI model nie je nakonfigurovaný v .env.',
            status=key_error_status,
        )
        return result, err, active_transits

    if active_transits is None:
        active_transits = _collect_ai_day_active_transits(profile, target_date, request=request)

    try:
        parsed, fallback_used, had_error, warning = _generate_ai_day_payload_for_model(
            profile,
            target_date,
            active_transits,
            model_ref,
        )
    except GeminiLimitExceededError:
        _record_ai_day_stats(normalized_ref, total_requests=1, errors_count=1)
        result, err = _build_ai_day_error_result(
            model_ref,
            'Denný limit AI volaní bol prekročený. Skúste to neskôr.',
            limit_exceeded=True,
            status=503,
        )
        return result, err, active_transits
    except AICreditLimitExceededError:
        _record_ai_day_stats(normalized_ref, total_requests=1, errors_count=1)
        result, err = _build_ai_day_error_result(
            model_ref,
            'Nedostatok AI kreditov. Dobite kredity a skús to znovu.',
            status=402,
        )
        return result, err, active_transits

    if fallback_used:
        parsed = dict(parsed or {})
        parsed['_fallback_used'] = True
        if warning:
            parsed['_warning'] = warning
        elif not parsed.get('_warning'):
            parsed['_warning'] = 'AI výstup bol neúplný, použitý je bezpečný fallback z tranzitov.'

    generated_at = _store_ai_day_report_cache(
        profile,
        target_date,
        normalized_ref,
        parsed,
    )
    _record_ai_day_stats(
        normalized_ref,
        total_requests=1,
        generated_reports=1,
        fallback_reports=1 if fallback_used else 0,
        errors_count=1 if had_error else 0,
    )

    response_payload = _build_ai_day_response_payload(
        parsed,
        active_model_ctx=active_model_ctx,
        generated_at=generated_at,
        cache_hit=False,
    )
    if warning:
        response_payload['warning'] = warning
    response_payload['ok'] = True
    return response_payload, None, active_transits


@login_required(login_url='transits:login')
@require_http_methods(["POST"])
def ai_day_report(request):
    """API endpoint - AI hodnotenie dňa (cache + metriky)."""
    try:
        body = json.loads(request.body or '{}')
        profile_id = body.get('profile_id')
        day_offset = int(body.get('day_offset', 0))
        model_ref_raw = str(body.get('model_ref') or '').strip()
    except (json.JSONDecodeError, TypeError, ValueError):
        active_model_ctx = get_active_model_context()
        model_ref = _normalize_ai_day_model_ref(active_model_ctx)
        _record_ai_day_stats(model_ref, total_requests=1, errors_count=1)
        return JsonResponse({'error': 'Neplatný request.'}, status=400)

    model_ref = model_ref_raw
    if model_ref_raw:
        validated_refs, model_ref_error = _validate_compare_model_refs(
            [model_ref_raw],
            max_items=1,
            user=request.user,
        )
        if model_ref_error:
            active_model_ctx = get_active_model_context()
            fallback_ref = _normalize_ai_day_model_ref(active_model_ctx)
            _record_ai_day_stats(fallback_ref, total_requests=1, errors_count=1)
            return JsonResponse({'error': model_ref_error}, status=400)
        model_ref = validated_refs[0]

    active_model_ctx = get_active_model_context(model_name=model_ref or None)
    if not model_ref:
        model_ref = _normalize_ai_day_model_ref(active_model_ctx)

    if day_offset < -30 or day_offset > 365:
        _record_ai_day_stats(model_ref, total_requests=1, errors_count=1)
        return JsonResponse({'error': 'day_offset je mimo povolený rozsah.'}, status=400)

    profile = get_object_or_404(NatalProfile, pk=profile_id)
    if not request.user.is_staff and profile.user_id != request.user.pk:
        _record_ai_day_stats(model_ref, total_requests=1, errors_count=1)
        return JsonResponse({'error': 'Nemáš prístup k tomuto profilu.'}, status=403)

    target_date = timezone.localdate() + timedelta(days=day_offset)
    result, err, _ = _get_or_generate_ai_day_report_for_model(
        profile,
        target_date,
        model_ref,
        request=request,
        active_transits=None,
        key_error_status=500,
    )
    if err:
        payload = {
            'error': err.get('error') or 'Nepodarilo sa získať AI hodnotenie dňa.',
            'ai_model_badge': err.get('ai_model_badge') or active_model_ctx.get('badge', 'AI'),
        }
        if err.get('limit_exceeded'):
            payload['limit_exceeded'] = True
        return JsonResponse(payload, status=err.get('status') or 500)

    result.pop('ok', None)
    return JsonResponse(result)


@login_required(login_url='transits:login')
@require_http_methods(["POST"])
def ai_day_report_compare(request):
    """API endpoint - porovnanie AI hodnotenia dňa medzi viacerými modelmi."""
    try:
        body = json.loads(request.body or '{}')
        profile_id = body.get('profile_id')
        day_offset = int(body.get('day_offset', 0))
        model_refs_raw = body.get('model_refs')
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'error': 'Neplatný request.'}, status=400)

    if day_offset < -30 or day_offset > 365:
        return JsonResponse({'error': 'day_offset je mimo povolený rozsah.'}, status=400)

    model_refs, model_refs_error = _validate_compare_model_refs(
        model_refs_raw,
        max_items=_get_compare_models_limit(),
        user=request.user,
    )
    if model_refs_error:
        return JsonResponse({'error': model_refs_error}, status=400)

    profile = get_object_or_404(NatalProfile, pk=profile_id)
    if not request.user.is_staff and profile.user_id != request.user.pk:
        return JsonResponse({'error': 'Nemáš prístup k tomuto profilu.'}, status=403)

    target_date = timezone.localdate() + timedelta(days=day_offset)
    active_transits = None
    results = []
    errors = []

    for model_ref in model_refs:
        item, err, active_transits = _get_or_generate_ai_day_report_for_model(
            profile,
            target_date,
            model_ref,
            request=request,
            active_transits=active_transits,
            key_error_status=503,
        )
        results.append(item)
        if err:
            errors.append({
                'model_ref': err.get('model_ref'),
                'ai_model_badge': err.get('ai_model_badge'),
                'error': err.get('error'),
                'limit_exceeded': bool(err.get('limit_exceeded')),
                'status': int(err.get('status') or 500),
            })

    success_count = sum(1 for item in results if item.get('ok'))
    status_code = 200
    if success_count == 0 and errors:
        if any((err.get('status') or 0) >= 500 for err in errors):
            status_code = 503
        elif any((err.get('status') or 0) == 402 for err in errors):
            status_code = 402
        else:
            status_code = 400

    return JsonResponse({
        'profile_id': profile.pk,
        'target_date': target_date.isoformat(),
        'day_offset': day_offset,
        'requested_model_refs': model_refs,
        'results': results,
        'errors': errors,
        'partial': bool(errors),
        'ok_models': success_count,
    }, status=status_code)


@login_required(login_url='transits:login')
@require_http_methods(["POST"])
def api_select_ai_model(request):
    """Prepne aktívny DEFAULT_MODEL cez header dropdown (staff alebo Pro účet, lazy bez live probe)."""
    if not user_can_switch_ai_model(request.user):
        return JsonResponse({'error': 'Nemáš oprávnenie meniť AI model.'}, status=403)

    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Neplatný JSON payload.'}, status=400)

    model_ref = str(body.get('model_ref') or '').strip()
    if not model_ref:
        return JsonResponse({'error': 'Chýba model_ref.'}, status=400)

    try:
        allowed_qs = AIModelOption.objects.filter(is_enabled=True, is_available=True)
        if not _can_access_pro_models(request.user):
            allowed_qs = allowed_qs.filter(is_pro_only=False)
        allowed = set(allowed_qs.values_list('model_ref', flat=True))
    except (OperationalError, ProgrammingError):
        allowed = set(
            AIModelOption.objects.filter(is_enabled=True).values_list('model_ref', flat=True)
        )
    if allowed and model_ref not in allowed:
        return JsonResponse({'error': 'Zvolený model nie je povolený v dropdown zozname.'}, status=400)

    has_key = has_ai_key(model_name=model_ref)

    cfg, _ = GeminiConfig.objects.get_or_create(id=1)
    if (cfg.default_model or '').strip() == model_ref:
        active = get_active_model_context(model_name=model_ref)
        response_payload = {
            'ok': True,
            'message': 'Model je už aktívny.',
            'active_badge': active.get('badge', model_ref),
            'users_total': NatalProfile.objects.count(),
            'users_ok': 0,
            'users_fail': 0,
            'users_marked': 0,
            'users_refresh_mode': 'lazy',
            'moment_report_date': '',
        }
        if not has_key:
            response_payload['warning'] = 'API kľúč pre Vercel AI Gateway chýba v .env (model bude používať fallback).'
        return JsonResponse(response_payload)

    cfg.default_model = model_ref
    cfg.save(update_fields=['default_model', 'updated_at'])

    total = NatalProfile.objects.count()
    ok = 0
    fail = 0
    users_marked = 0
    refresh_users_raw = body.get('refresh_users')
    if refresh_users_raw is None:
        eager_users_refresh = bool(getattr(settings, 'AI_MODEL_SWITCH_EAGER_USERS_REFRESH', False))
    else:
        eager_users_refresh = str(refresh_users_raw).strip().lower() in ('1', 'true', 'yes', 'on')
    try:
        if eager_users_refresh:
            for profile in NatalProfile.objects.all().iterator():
                if _generate_and_save_analyses(profile, model_name=model_ref):
                    ok += 1
                else:
                    fail += 1
            refresh_mode = 'eager'
        else:
            users_marked = _invalidate_all_natal_analyses()
            refresh_mode = 'lazy'

        active = get_active_model_context(model_name=model_ref)
        response_payload = {
            'ok': True,
            'message': (
                'AI model bol prepnutý. Natálne analýzy budú regenerované lazy pri ďalšej návšteve používateľa.'
                if refresh_mode == 'lazy'
                else 'AI model bol prepnutý a používateľské analýzy boli zregenerované.'
            ),
            'active_badge': active.get('badge', model_ref),
            'users_total': total,
            'users_ok': ok,
            'users_fail': fail,
            'users_marked': users_marked,
            'users_refresh_mode': refresh_mode,
            'moment_report_date': '',
            'moment_refresh_mode': 'lazy',
        }
        if not has_key:
            response_payload['warning'] = 'API kľúč pre Vercel AI Gateway chýba v .env (model bude používať fallback).'
        return JsonResponse(response_payload)
    except Exception as exc:
        logger.error("Prepnutie modelu na %s zlyhalo počas refreshu: %s", model_ref, exc)
        return JsonResponse({
            'error': f'Model bol prepnutý, ale refresh natálnych analýz zlyhal: {exc}',
            'partial': True,
        }, status=500)
