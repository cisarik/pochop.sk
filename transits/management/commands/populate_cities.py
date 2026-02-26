"""
Management command na naplnenie databázy slovenských obcí.
Obsahuje všetkých 79 okresných miest + ďalšie väčšie obce (~150+).
"""
from django.core.management.base import BaseCommand
from transits.models import SlovakCity


# (názov, okres, lat, lon)
CITIES_DATA = [
    # === KRAJSKÉ MESTÁ ===
    ("Bratislava", "Bratislava", 48.1486, 17.1077),
    ("Trnava", "Trnava", 48.3774, 17.5876),
    ("Trenčín", "Trenčín", 48.8945, 18.0444),
    ("Nitra", "Nitra", 48.3069, 18.0864),
    ("Žilina", "Žilina", 49.2231, 18.7394),
    ("Banská Bystrica", "Banská Bystrica", 48.7363, 19.1461),
    ("Prešov", "Prešov", 48.9984, 21.2354),
    ("Košice", "Košice", 48.7164, 21.2611),

    # === OKRESNÉ MESTÁ ===
    ("Senec", "Senec", 48.2197, 17.4003),
    ("Pezinok", "Pezinok", 48.2892, 17.2673),
    ("Malacky", "Malacky", 48.4363, 17.0244),
    ("Dunajská Streda", "Dunajská Streda", 47.9933, 17.6181),
    ("Galanta", "Galanta", 48.1903, 17.7261),
    ("Hlohovec", "Hlohovec", 48.4318, 17.8019),
    ("Piešťany", "Piešťany", 48.5944, 17.8283),
    ("Senica", "Senica", 48.6800, 17.3667),
    ("Skalica", "Skalica", 48.8453, 17.2258),
    ("Bánovce nad Bebravou", "Bánovce nad Bebravou", 48.7189, 18.2583),
    ("Ilava", "Ilava", 48.9963, 18.2332),
    ("Myjava", "Myjava", 48.7558, 17.5683),
    ("Nové Mesto nad Váhom", "Nové Mesto nad Váhom", 48.7581, 17.8303),
    ("Partizánske", "Partizánske", 48.6289, 18.3764),
    ("Považská Bystrica", "Považská Bystrica", 49.1217, 18.4214),
    ("Prievidza", "Prievidza", 48.7742, 18.6247),
    ("Púchov", "Púchov", 49.1197, 18.3261),
    ("Komárno", "Komárno", 47.7633, 18.1286),
    ("Levice", "Levice", 48.2172, 18.5992),
    ("Nové Zámky", "Nové Zámky", 47.9857, 18.1619),
    ("Šaľa", "Šaľa", 48.1517, 17.8717),
    ("Topoľčany", "Topoľčany", 48.5617, 18.1756),
    ("Zlaté Moravce", "Zlaté Moravce", 48.3808, 18.4003),
    ("Bytča", "Bytča", 49.2233, 18.5583),
    ("Čadca", "Čadca", 49.4381, 18.7878),
    ("Dolný Kubín", "Dolný Kubín", 49.2094, 19.2972),
    ("Kysucké Nové Mesto", "Kysucké Nové Mesto", 49.3000, 18.7833),
    ("Liptovský Mikuláš", "Liptovský Mikuláš", 49.0839, 19.6114),
    ("Martin", "Martin", 49.0636, 18.9214),
    ("Námestovo", "Námestovo", 49.4069, 19.4789),
    ("Ružomberok", "Ružomberok", 49.0756, 19.3069),
    ("Turčianske Teplice", "Turčianske Teplice", 48.8667, 18.8583),
    ("Tvrdošín", "Tvrdošín", 49.3372, 19.5556),
    ("Banská Štiavnica", "Banská Štiavnica", 48.4589, 18.8928),
    ("Brezno", "Brezno", 48.8069, 19.6369),
    ("Detva", "Detva", 48.5564, 19.4222),
    ("Krupina", "Krupina", 48.3550, 19.0692),
    ("Lučenec", "Lučenec", 48.3272, 19.6672),
    ("Poltár", "Poltár", 48.4314, 19.7922),
    ("Revúca", "Revúca", 48.6833, 20.1167),
    ("Rimavská Sobota", "Rimavská Sobota", 48.3828, 20.0219),
    ("Veľký Krtíš", "Veľký Krtíš", 48.2125, 19.3489),
    ("Zvolen", "Zvolen", 48.5756, 19.1361),
    ("Žarnovica", "Žarnovica", 48.4833, 18.7167),
    ("Žiar nad Hronom", "Žiar nad Hronom", 48.5906, 18.8544),
    ("Bardejov", "Bardejov", 49.2925, 21.2769),
    ("Humenné", "Humenné", 48.9356, 21.9064),
    ("Kežmarok", "Kežmarok", 49.1344, 20.4289),
    ("Levoča", "Levoča", 49.0250, 20.5903),
    ("Medzilaborce", "Medzilaborce", 49.2714, 21.9042),
    ("Poprad", "Poprad", 49.0597, 20.2981),
    ("Sabinov", "Sabinov", 49.1028, 21.0972),
    ("Snina", "Snina", 48.9878, 22.1536),
    ("Stará Ľubovňa", "Stará Ľubovňa", 49.3000, 20.6833),
    ("Stropkov", "Stropkov", 49.2028, 21.6511),
    ("Svidník", "Svidník", 49.3069, 21.5708),
    ("Vranov nad Topľou", "Vranov nad Topľou", 48.8844, 21.6853),
    ("Gelnica", "Gelnica", 48.8567, 20.9372),
    ("Košice-okolie", "Košice-okolie", 48.7164, 21.2611),
    ("Michalovce", "Michalovce", 48.7544, 21.9219),
    ("Rožňava", "Rožňava", 48.6603, 20.5336),
    ("Sobrance", "Sobrance", 48.7458, 22.1803),
    ("Spišská Nová Ves", "Spišská Nová Ves", 48.9464, 20.5689),
    ("Trebišov", "Trebišov", 48.6292, 21.7153),

    # === ĎALŠIE VÄČŠIE MESTÁ A OBCE ===
    ("Šamorín", "Dunajská Streda", 48.0264, 17.3117),
    ("Stupava", "Malacky", 48.2758, 17.0317),
    ("Svätý Jur", "Pezinok", 48.2497, 17.2150),
    ("Modra", "Pezinok", 48.3356, 17.3069),
    ("Bernolákovo", "Senec", 48.1978, 17.2997),
    ("Ivanka pri Dunaji", "Senec", 48.1833, 17.2583),
    ("Leopoldov", "Hlohovec", 48.4478, 17.7678),
    ("Vrbové", "Piešťany", 48.6164, 17.7244),
    ("Sereď", "Galanta", 48.2844, 17.7333),
    ("Šaštín-Stráže", "Senica", 48.6347, 17.1472),
    ("Holíč", "Skalica", 48.8092, 17.1608),
    ("Gbely", "Skalica", 48.7183, 17.1169),
    ("Dubnica nad Váhom", "Ilava", 48.9583, 18.1703),
    ("Nemšová", "Trenčín", 48.9667, 18.1167),
    ("Handlová", "Prievidza", 48.7297, 18.7631),
    ("Bojnice", "Prievidza", 48.7797, 18.5803),
    ("Nováky", "Prievidza", 48.7186, 18.5358),
    ("Stará Turá", "Nové Mesto nad Váhom", 48.7772, 17.6983),
    ("Brezová pod Bradlom", "Myjava", 48.6647, 17.5356),
    ("Hurbanovo", "Komárno", 47.8731, 18.1917),
    ("Kolárovo", "Komárno", 47.9222, 17.9892),
    ("Štúrovo", "Nové Zámky", 47.7981, 18.7158),
    ("Želiezovce", "Levice", 47.9861, 18.6594),
    ("Šurany", "Nové Zámky", 48.0847, 18.1856),
    ("Tvrdošovce", "Nové Zámky", 48.0917, 18.0500),
    ("Vráble", "Nitra", 48.2422, 18.3100),
    ("Šahy", "Levice", 48.0692, 18.9556),
    ("Turzovka", "Čadca", 49.4053, 18.6244),
    ("Krásno nad Kysucou", "Čadca", 49.3917, 18.8333),
    ("Trstená", "Tvrdošín", 49.3647, 19.6128),
    ("Vrútky", "Martin", 49.1128, 18.9208),
    ("Žiar nad Hronom", "Žiar nad Hronom", 48.5906, 18.8544),
    ("Sliač", "Zvolen", 48.6092, 19.1453),
    ("Fiľakovo", "Lučenec", 48.2711, 19.8281),
    ("Tornaľa", "Revúca", 48.4181, 20.3358),
    ("Hnúšťa", "Rimavská Sobota", 48.5756, 19.9658),
    ("Tisovec", "Rimavská Sobota", 48.6828, 19.9422),
    ("Svit", "Poprad", 49.0547, 20.2097),
    ("Vysoké Tatry", "Poprad", 49.1392, 20.2303),
    ("Spišské Podhradie", "Levoča", 49.0003, 20.7503),
    ("Lipany", "Sabinov", 49.1528, 20.9728),
    ("Giraltovce", "Svidník", 49.1167, 21.5167),
    ("Hanušovce nad Topľou", "Vranov nad Topľou", 49.0256, 21.4953),
    ("Veľké Kapušany", "Michalovce", 48.5444, 22.0750),
    ("Strážske", "Michalovce", 48.8722, 21.8222),
    ("Moldava nad Bodvou", "Košice-okolie", 48.6086, 20.9994),
    ("Medzev", "Košice-okolie", 48.7000, 20.8917),
    ("Krompachy", "Spišská Nová Ves", 48.9153, 20.8736),
    ("Dobšiná", "Rožňava", 48.8192, 20.3639),
    ("Kráľovský Chlmec", "Trebišov", 48.4222, 21.9833),
    ("Sečovce", "Trebišov", 48.7000, 21.6667),
    ("Snežienková", "Bratislava", 48.1700, 17.0600),
    ("Devínska Nová Ves", "Bratislava", 48.2069, 16.9789),
    ("Petržalka", "Bratislava", 48.1322, 17.1186),
    ("Ružinov", "Bratislava", 48.1569, 17.1831),
    ("Karlova Ves", "Bratislava", 48.1594, 17.0569),
    ("Devín", "Bratislava", 48.1747, 16.9797),
    ("Rača", "Bratislava", 48.2044, 17.1528),
    ("Vajnory", "Bratislava", 48.2000, 17.2000),
    ("Podunajské Biskupice", "Bratislava", 48.1333, 17.2000),
    ("Lamač", "Bratislava", 48.1903, 17.0472),
    ("Dúbravka", "Bratislava", 48.1950, 17.0406),
    ("Nové Mesto", "Bratislava", 48.1667, 17.1333),
    ("Staré Mesto", "Bratislava", 48.1450, 17.1078),

    # === ĎALŠIE OBCE ===
    ("Žiar", "Žilina", 49.2167, 18.7500),
    ("Rajec", "Žilina", 49.0864, 18.6378),
    ("Rajecké Teplice", "Žilina", 49.1397, 18.6917),
    ("Čierne", "Čadca", 49.4833, 18.8333),
    ("Skalité", "Čadca", 49.5000, 18.8833),
    ("Zuberec", "Tvrdošín", 49.2628, 19.6097),
    ("Oravský Podzámok", "Dolný Kubín", 49.2583, 19.3556),
    ("Habovka", "Tvrdošín", 49.2653, 19.5922),
    ("Terchová", "Žilina", 49.2603, 19.0256),
    ("Kremnica", "Žiar nad Hronom", 48.7053, 18.9181),
    ("Nová Baňa", "Žarnovica", 48.4269, 18.6375),
    ("Dudince", "Krupina", 48.1683, 18.8858),
    ("Modrý Kameň", "Veľký Krtíš", 48.2431, 19.3372),
    ("Jesenské", "Rimavská Sobota", 48.3414, 19.9311),
    ("Kokava nad Rimavicou", "Poltár", 48.5297, 19.8444),
    ("Hriňová", "Detva", 48.5903, 19.5269),
    ("Podbrezová", "Brezno", 48.8167, 19.5333),
    ("Čierny Balog", "Brezno", 48.7500, 19.6667),
    ("Ždiar", "Poprad", 49.2717, 20.2667),
    ("Červený Kláštor", "Kežmarok", 49.3892, 20.4119),
    ("Podolínec", "Stará Ľubovňa", 49.2597, 20.5372),
    ("Spišské Vlachy", "Spišská Nová Ves", 48.9500, 20.7833),
    ("Smižany", "Spišská Nová Ves", 48.9464, 20.5333),
    ("Smolník", "Gelnica", 48.7500, 20.7167),
    ("Poproč", "Košice-okolie", 48.7000, 21.0500),
    ("Čaňa", "Košice-okolie", 48.6333, 21.3333),
    ("Šaca", "Košice", 48.6333, 21.2167),
    ("Krásna", "Košice", 48.6667, 21.3000),
    ("Ťahanovce", "Košice", 48.7500, 21.2500),
    ("Sídlisko KVP", "Košice", 48.7167, 21.2167),
    ("Košická Nová Ves", "Košice", 48.6833, 21.2833),
    ("Čierna nad Tisou", "Trebišov", 48.4167, 22.0833),
    ("Borša", "Trebišov", 48.3500, 21.7333),
    ("Slovenské Nové Mesto", "Trebišov", 48.4333, 21.7500),
    ("Vinné", "Michalovce", 48.7833, 22.0167),
    ("Zemplínska Šírava", "Michalovce", 48.7833, 21.9833),
    ("Frýdek-Místek", "Frýdek-Místek", 49.6881, 18.3508),
    ("Ostrava", "Ostrava", 49.8209, 18.2625),
    ("Praha", "Praha", 50.0755, 14.4378),
    ("Brno", "Brno", 49.1951, 16.6068),

    # === POPULÁRNE OBCE A DEDINY ===
    ("Štrba", "Poprad", 49.0583, 20.0667),
    ("Liptovský Hrádok", "Liptovský Mikuláš", 49.0394, 19.7225),
    ("Liptovský Ján", "Liptovský Mikuláš", 49.0333, 19.6833),
    ("Demänovská Dolina", "Liptovský Mikuláš", 49.0000, 19.5833),
    ("Oravská Lesná", "Námestovo", 49.3667, 19.1833),
    ("Zákopčie", "Čadca", 49.4167, 18.7167),
    ("Korňa", "Čadca", 49.3333, 18.6167),
    ("Raková", "Čadca", 49.4833, 18.7167),
    ("Oščadnica", "Čadca", 49.4500, 18.8167),
    ("Veľká Lomnica", "Kežmarok", 49.1000, 20.3500),
    ("Vrbov", "Kežmarok", 49.1000, 20.4000),
    ("Tatranská Lomnica", "Poprad", 49.1667, 20.2833),
    ("Starý Smokovec", "Poprad", 49.1389, 20.2250),
    ("Štrbské Pleso", "Poprad", 49.1186, 20.0619),
    ("Východná", "Liptovský Mikuláš", 49.0667, 19.8833),
    ("Vlkolínec", "Ružomberok", 49.0406, 19.2775),
    ("Čičmany", "Žilina", 48.9500, 18.5333),
    ("Donovaly", "Banská Bystrica", 48.8833, 19.2167),
]


class Command(BaseCommand):
    help = 'Naplní databázu slovenských obcí s GPS súradnicami'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Vymaže existujúce obce pred importom'
        )

    def handle(self, *args, **options):
        if options['reset']:
            deleted = SlovakCity.objects.all().delete()[0]
            self.stdout.write(f'Vymazaných {deleted} obcí.')

        created = 0
        skipped = 0
        seen = set()

        for name, district, lat, lon in CITIES_DATA:
            key = (name, district)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)

            _, was_created = SlovakCity.objects.get_or_create(
                name=name,
                district=district,
                defaults={'lat': lat, 'lon': lon},
            )
            if was_created:
                created += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'Hotovo! Vytvorených: {created}, preskočených: {skipped}, '
            f'celkom v DB: {SlovakCity.objects.count()}'
        ))
