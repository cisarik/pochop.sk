"""
Kompletná databáza výkladov tranzitových aspektov v slovenčine.
Každý záznam: (transit_planet, natal_planet, aspect_type, effect, text_sk)
"""

# Efekty aspektov: harmonické = pozitívne, napäťové = negatívne
# conjunction závisí od planét
HARMONIOUS = ('trine', 'sextile')
CHALLENGING = ('square', 'opposition')


def _build_transit_entries():
    """Generuje všetky kombinácie tranzitov s výkladmi v slovenčine."""
    entries = []

    # ═══════════════════════════════════════════════════
    # TRANZITY SLNKA (t.Slnko)
    # ═══════════════════════════════════════════════════

    # t.Slnko - n.Slnko
    entries.extend([
        ('sun', 'sun', 'conjunction', 'positive',
         'Solárny návrat - nový osobný rok. Čas na stanovenie cieľov a zámerov na nasledujúce obdobie. Zvýšená vitalita a sebavedomie. Príležitosť na nový začiatok.'),
        ('sun', 'sun', 'sextile', 'positive',
         'Harmonický tok energie podporuje sebavyjadrenie a tvorivosť. Dobré obdobie pre osobné projekty a iniciatívy.'),
        ('sun', 'sun', 'square', 'negative',
         'Vnútorné napätie medzi tým, kým ste a kým chcete byť. Konflikty s autoritami. Potreba prehodnotiť svoje smerovanie.'),
        ('sun', 'sun', 'trine', 'positive',
         'Plynulý tok vitality a sebavedomia. Ľahko sa presadzujete a dosahujete ciele. Dobrá doba na osobný rast.'),
        ('sun', 'sun', 'opposition', 'negative',
         'Konfrontácia s vlastnou identitou. Vzťahy s ostatnými odhaľujú vaše silné a slabé stránky. Čas na rovnováhu medzi ja a ty.'),
    ])

    # t.Slnko - n.Mesiac
    entries.extend([
        ('sun', 'moon', 'conjunction', 'positive',
         'Harmónia medzi vôľou a citmi. Zvýšená emocionálna vyrovnanosť. Dobré obdobie pre rodinné záležitosti a domov.'),
        ('sun', 'moon', 'sextile', 'positive',
         'Emocionálna pohoda a vnútorný pokoj. Príjemné interakcie s rodinou. Tvorivá inšpirácia.'),
        ('sun', 'moon', 'square', 'negative',
         'Napätie medzi osobnými potrebami a emóciami. Konflikty v rodine alebo domácnosti. Vnútorný nepokoj.'),
        ('sun', 'moon', 'trine', 'positive',
         'Emocionálna rovnováha a vnútorný pokoj. Harmónia medzi vedomím a podvedomím. Ideálne pre rodinné stretnutia.'),
        ('sun', 'moon', 'opposition', 'negative',
         'Napätie medzi rozumom a citmi. Konflikty medzi prácou a domovom. Emocionálna nerovnováha.'),
    ])

    # t.Slnko - n.Merkúr
    entries.extend([
        ('sun', 'mercury', 'conjunction', 'positive',
         'Jasné myslenie a výborná komunikácia. Ideálne pre dôležité rozhovory, podpisy zmlúv, učenie sa.'),
        ('sun', 'mercury', 'sextile', 'positive',
         'Mentálna čulosť a schopnosť dobre komunikovať. Dobré obdobie pre obchodné rokovania.'),
        ('sun', 'mercury', 'square', 'negative',
         'Nedorozumenia a komunikačné problémy. Nepremyslené vyjadrenia môžu spôsobiť konflikty. Pozor na podpisy dokumentov.'),
        ('sun', 'mercury', 'trine', 'positive',
         'Výborné mentálne schopnosti. Jasné myslenie, úspešné rokovania. Ideálne pre štúdium a komunikáciu.'),
        ('sun', 'mercury', 'opposition', 'negative',
         'Rozdielne názory s okolím. Komunikačné prekážky. Iní ľudia vás nemusia pochopiť. Buďte trpezliví.'),
    ])

    # t.Slnko - n.Venuša
    entries.extend([
        ('sun', 'venus', 'conjunction', 'positive',
         'Zvýšená príťažlivosť a šarm. Romantické stretnutia, pôžitky, krása. Dobré pre lásku, umenie, nakupovanie.'),
        ('sun', 'venus', 'sextile', 'positive',
         'Príjemné spoločenské kontakty a harmónia vo vzťahoch. Estetické potešenie, tvorivosť.'),
        ('sun', 'venus', 'square', 'negative',
         'Napätie vo vzťahoch, extravagancia, lenivosť. Sklon k prejedaniu alebo nadmernému míňaniu peňazí.'),
        ('sun', 'venus', 'trine', 'positive',
         'Krásny deň pre lásku, romantiku, umenie. Harmónia vo vzťahoch. Finančné príležitosti.'),
        ('sun', 'venus', 'opposition', 'negative',
         'Napätie vo vzťahoch a hodnotách. Konflikty kvôli peniazom alebo láske. Túžba po pôžitkoch.'),
    ])

    # t.Slnko - n.Mars
    entries.extend([
        ('sun', 'mars', 'conjunction', 'neutral',
         'Zvýšená energia a iniciatíva. Silná vôľa a odhodlanie. Pozor na impulzívnosť a konflikty.'),
        ('sun', 'mars', 'sextile', 'positive',
         'Produktívna energia. Schopnosť efektívne konať a presadzovať sa. Dobrý deň pre šport a fyzickú aktivitu.'),
        ('sun', 'mars', 'square', 'negative',
         'Konflikty, hádky, impulzívne konanie. Zvýšené riziko úrazov. Netrpezlivosť a agresivita. Vyhnite sa konfrontáciám.'),
        ('sun', 'mars', 'trine', 'positive',
         'Dynamická energia a odvaha. Úspešné presadzovanie záujmov. Vynikajúce pre šport a podnikanie.'),
        ('sun', 'mars', 'opposition', 'negative',
         'Konfrontácie s ostatnými. Mocenské boje. Zvýšená podráždenosť. Riziko úrazov pri nepozornosti.'),
    ])

    # t.Slnko - n.Jupiter
    entries.extend([
        ('sun', 'jupiter', 'conjunction', 'positive',
         'Optimizmus, šťastie, rozšírenie obzorov. Príležitosti pre rast a úspech. Štedrý a veľkorysý deň.'),
        ('sun', 'jupiter', 'sextile', 'positive',
         'Príjemné príležitosti a pozitívna nálada. Podpora od nadriadených. Dobré pre cestovanie a vzdelávanie.'),
        ('sun', 'jupiter', 'square', 'negative',
         'Prehnané ambície a prehnaný optimizmus. Sklon k extravagancii. Pozor na sľuby, ktoré nemôžete dodržať.'),
        ('sun', 'jupiter', 'trine', 'positive',
         'Skvelé obdobie pre osobný rast, cestovanie, vzdelávanie. Šťastie a optimizmus. Úspech v podnikoch.'),
        ('sun', 'jupiter', 'opposition', 'negative',
         'Prehnaný optimizmus a nadmerná sebadôvera. Tendencie k prehnanému míňaniu. Konflikty s autoritami.'),
    ])

    # t.Slnko - n.Saturn
    entries.extend([
        ('sun', 'saturn', 'conjunction', 'negative',
         'Pocit obmedzenia a zodpovednosti. Nízka energia. Čas na disciplínu a tvrdú prácu. Výsledky prídu neskôr.'),
        ('sun', 'saturn', 'sextile', 'positive',
         'Disciplinovaná práca prináša výsledky. Stabilita a organizácia. Dobrý deň pre plánovanie a štruktúru.'),
        ('sun', 'saturn', 'square', 'negative',
         'Frustrácia, prekážky, oneskorenia. Pocit, že ste pod tlakom. Konflikty s autoritami. Nízka vitalita.'),
        ('sun', 'saturn', 'trine', 'positive',
         'Produktívna disciplína. Praktické výsledky. Uznanie od nadriadených. Stabilný pokrok v kariére.'),
        ('sun', 'saturn', 'opposition', 'negative',
         'Konfrontácia s realitou a zodpovednosťou. Pocit osamelosti alebo izolácie. Zdravotné ťažkosti sú možné.'),
    ])

    # t.Slnko - n.Urán
    entries.extend([
        ('sun', 'uranus', 'conjunction', 'neutral',
         'Náhle zmeny a prekvapenia. Túžba po slobode a originalite. Neočakávané udalosti môžu zmeniť smerovanie.'),
        ('sun', 'uranus', 'sextile', 'positive',
         'Inšpirácia a originalita. Príjemné prekvapenia. Nové kontakty s nekonvenčnými ľuďmi.'),
        ('sun', 'uranus', 'square', 'negative',
         'Náhle narušenia a nepokoje. Impulzívne rozhodnutia. Nervozita a netrpezlivosť. Pozor na nehody.'),
        ('sun', 'uranus', 'trine', 'positive',
         'Pozitívne zmeny a vzrušujúce príležitosti. Originalita a inovácia. Oslobodzujúci pocit.'),
        ('sun', 'uranus', 'opposition', 'negative',
         'Neočakávané konfrontácie a zmeny. Iní ľudia narúšajú vaše plány. Potreba prispôsobenia.'),
    ])

    # t.Slnko - n.Neptún
    entries.extend([
        ('sun', 'neptune', 'conjunction', 'neutral',
         'Zvýšená citlivosť a intuícia. Sny a vízie. Riziko sebaklamania. Dobrý čas pre meditáciu a umenie.'),
        ('sun', 'neptune', 'sextile', 'positive',
         'Inšpirácia a duchovné vnímanie. Empatia a súcit. Dobré pre tvorivú prácu a pomoc iným.'),
        ('sun', 'neptune', 'square', 'negative',
         'Zmätok a dezilúzia. Nejasnosti a podvod. Vyhnite sa dôležitým rozhodnutiam. Pozor na alkohol a lieky.'),
        ('sun', 'neptune', 'trine', 'positive',
         'Duchovná harmónia a umelecká inšpirácia. Hlboká intuícia. Ideálne pre meditáciu a tvorivú prácu.'),
        ('sun', 'neptune', 'opposition', 'negative',
         'Klam a dezilúzia vo vzťahoch. Strata energie. Vyhnite sa finančným špekuláciám. Pozor na podvod.'),
    ])

    # t.Slnko - n.Pluto
    entries.extend([
        ('sun', 'pluto', 'conjunction', 'neutral',
         'Intenzívna transformácia a obnova. Mocné vnútorné zmeny. Konfrontácia s hlbokými pravdami.'),
        ('sun', 'pluto', 'sextile', 'positive',
         'Pozitívna transformácia a obnova. Hlboké porozumenie situáciám. Moc a vplyv.'),
        ('sun', 'pluto', 'square', 'negative',
         'Mocenské boje a kontrola. Intenzívne konflikty. Manipulácia. Potreba nechať odísť to, čo neslúži.'),
        ('sun', 'pluto', 'trine', 'positive',
         'Pozitívna regenerácia a transformácia. Hlboká sebaistota. Schopnosť prekonať prekážky.'),
        ('sun', 'pluto', 'opposition', 'negative',
         'Mocenské konfrontácie s ostatnými. Intenzívne vzťahové dynamiky. Potreba transformácie.'),
    ])

    # ═══════════════════════════════════════════════════
    # TRANZITY MESIACA (t.Mesiac) - rýchle, denné tranzity
    # ═══════════════════════════════════════════════════

    # t.Mesiac - n.Slnko
    entries.extend([
        ('moon', 'sun', 'conjunction', 'positive',
         'Novmesiac na vašom Slnku - emocionálny nový začiatok. Harmónia medzi citmi a vôľou. Vnútorná rovnováha.'),
        ('moon', 'sun', 'sextile', 'positive',
         'Príjemná nálada a emočná vyrovnanosť. Dobré vzťahy s okolím. Podpora v osobných záležitostiach.'),
        ('moon', 'sun', 'square', 'negative',
         'Emocionálne napätie a vnútorný nepokoj. Konflikty medzi potrebami a povinnosťami.'),
        ('moon', 'sun', 'trine', 'positive',
         'Emocionálna harmónia a pohoda. Cítite sa v rovnováhe. Príjemné stretnutia a zážitky.'),
        ('moon', 'sun', 'opposition', 'negative',
         'Spln na vašom Slnku - emočná kulminačná fáza. Napätie medzi ja a okolím. Dôležité uvedomenia.'),
    ])

    # t.Mesiac - n.Mesiac
    entries.extend([
        ('moon', 'moon', 'conjunction', 'positive',
         'Lunárny návrat - nový emocionálny cyklus. Zvýšená citlivosť a intuícia. Čas na starostlivosť o seba.'),
        ('moon', 'moon', 'sextile', 'positive',
         'Príjemná nálada a emocionálny tok. Dobré pre rodinné aktivity a domácnosť.'),
        ('moon', 'moon', 'square', 'negative',
         'Emocionálne napätie a podráždenosť. Vnútorný nepokoj. Staré emočné vzorce sa aktivujú.'),
        ('moon', 'moon', 'trine', 'positive',
         'Emocionálna harmónia a pohodlie. Príjemné spomienky a pocit bezpečia. Dobrý čas pre relaxáciu.'),
        ('moon', 'moon', 'opposition', 'negative',
         'Emocionálna konfrontácia. Napätie medzi potrebami a vonkajšími požiadavkami. Pocit rozpoltenosti.'),
    ])

    # t.Mesiac - n.Merkúr
    entries.extend([
        ('moon', 'mercury', 'conjunction', 'positive',
         'Emocionálna komunikácia. Schopnosť vyjadriť city slovami. Dobré pre dôverné rozhovory.'),
        ('moon', 'mercury', 'sextile', 'positive',
         'Plynulá komunikácia s citovým podtónom. Dobré pre písanie a vyjadrovanie myšlienok.'),
        ('moon', 'mercury', 'square', 'negative',
         'Emocionálne reagovanie v komunikácii. Nedorozumenia kvôli nálada. Unáhlené vyjadrenia.'),
        ('moon', 'mercury', 'trine', 'positive',
         'Harmónia medzi citmi a rozumom. Výborná intuícia. Empatická komunikácia.'),
        ('moon', 'mercury', 'opposition', 'negative',
         'Napätie medzi tým, čo cítite a čo hovoríte. Emocionálne zaťažená komunikácia.'),
    ])

    # t.Mesiac - n.Venuša
    entries.extend([
        ('moon', 'venus', 'conjunction', 'positive',
         'Romantická a nežná nálada. Túžba po kráse, harmónii a láske. Príjemný deň pre vzťahy.'),
        ('moon', 'venus', 'sextile', 'positive',
         'Príjemné spoločenské chvíle. Pocit krásy a harmónie. Dobrý čas pre umenie a relaxáciu.'),
        ('moon', 'venus', 'square', 'negative',
         'Emocionálna neistota vo vzťahoch. Prejedanie sa alebo nadmerné míňanie pre útechu.'),
        ('moon', 'venus', 'trine', 'positive',
         'Krásna nálada plná lásky a harmónie. Romantické chvíle. Estetické pôžitky.'),
        ('moon', 'venus', 'opposition', 'negative',
         'Napätie vo vzťahoch kvôli emóciám. Neistota v láske. Potreba emocionálneho potvrdenia.'),
    ])

    # t.Mesiac - n.Mars
    entries.extend([
        ('moon', 'mars', 'conjunction', 'neutral',
         'Zvýšená emocionálna energia a impulzívnosť. Vášnivé reakcie. Produktívna energia ak je kontrolovaná.'),
        ('moon', 'mars', 'sextile', 'positive',
         'Emocionálna odvaha a rozhodnosť. Schopnosť konať na základe intuície. Aktívny deň.'),
        ('moon', 'mars', 'square', 'negative',
         'Podráždenosť a emocionálna výbušnosť. Hádky a konflikty. Netrpezlivosť s najbližšími.'),
        ('moon', 'mars', 'trine', 'positive',
         'Zdravá emocionálna energia. Odvaha čeliť výzvam. Dobrý deň pre šport a fyzickú aktivitu.'),
        ('moon', 'mars', 'opposition', 'negative',
         'Emocionálne konfrontácie a hádky. Impulzívne reakcie. Pozor na agresivitu v blízkych vzťahoch.'),
    ])

    # t.Mesiac - n.Jupiter
    entries.extend([
        ('moon', 'jupiter', 'conjunction', 'positive',
         'Pocit šťastia a hojnosti. Optimistická nálada. Štedrť a veľkorysosť. Príjemné spoločenské udalosti.'),
        ('moon', 'jupiter', 'sextile', 'positive',
         'Dobrá nálada a optimizmus. Emocionálna štedrť. Príležitosti pre rast cez emocionálne zážitky.'),
        ('moon', 'jupiter', 'square', 'negative',
         'Špatná nálada, nespokojnosť, rozmary môžu spôsobiť hádky, nepriaznivé zmeny, dlhy. Ohováranie, špatná spoločnosť. Zlá doba pre manželstvo. Nepriaznivé zásahy okolia. Nepriateľstvo, poníženie, ohováranie.'),
        ('moon', 'jupiter', 'trine', 'positive',
         'Pocit vnútorného šťastia a harmónie. Pozitívne emocionálne zážitky. Dobrý čas pre rodinné oslavy.'),
        ('moon', 'jupiter', 'opposition', 'negative',
         'Prehnaná emocionalita a nestriedmosť. Sklon k emocionálnemu prejedaniu. Prehnané očakávania.'),
    ])

    # t.Mesiac - n.Saturn
    entries.extend([
        ('moon', 'saturn', 'conjunction', 'negative',
         'Emocionálna tiaž a melanchólia. Pocit osamelosti alebo izolácie. Zodpovednosti vás zaťažujú.'),
        ('moon', 'saturn', 'sextile', 'positive',
         'Emocionálna stabilita a vyrovnanosť. Schopnosť disciplinovane zvládať pocity.'),
        ('moon', 'saturn', 'square', 'negative',
         'Emocionálne obmedzenia a frustrácia. Pesimizmus a smútok. Pocit, že nie ste dosť dobrí.'),
        ('moon', 'saturn', 'trine', 'positive',
         'Emocionálna zrelosť a stabilita. Pokojné zvládanie zodpovedností. Vnútorná sila.'),
        ('moon', 'saturn', 'opposition', 'negative',
         'Emočný chlad od okolia. Pocit odmietnutia. Ťažkosti v rodinných vzťahoch. Melanchólia.'),
    ])

    # t.Mesiac - n.Urán
    entries.extend([
        ('moon', 'uranus', 'conjunction', 'neutral',
         'Náhle zmeny nálady a neočakávané emócie. Túžba po slobode. Vzrušujúce, ale nestabilné obdobie.'),
        ('moon', 'uranus', 'sextile', 'positive',
         'Príjemné prekvapenia a vzrušujúce emocionálne zážitky. Inšpirácia a originalita.'),
        ('moon', 'uranus', 'square', 'negative',
         'Emocionálna nestabilita a nervozita. Náhle výbuchy. Nečakané zmeny v domácnosti.'),
        ('moon', 'uranus', 'trine', 'positive',
         'Osviežujúce emočné zážitky. Príjemné prekvapenia. Pocit slobody a nezávislosti.'),
        ('moon', 'uranus', 'opposition', 'negative',
         'Emocionálne otrasenia od iných ľudí. Nečakané narušenia pokoja. Nervozita.'),
    ])

    # t.Mesiac - n.Neptún
    entries.extend([
        ('moon', 'neptune', 'conjunction', 'neutral',
         'Možnosť zmeniť emocionálne sny a sny o domácnosti na skutočnosť. Skôr však možné zmätky, nepraktickosť.'),
        ('moon', 'neptune', 'sextile', 'positive',
         'Zvýšená intuícia a empatia. Krásne sny a umelecká inšpirácia. Duchovné vnímanie.'),
        ('moon', 'neptune', 'square', 'negative',
         'Emocionálny zmätok a dezilúzia. Sklon k úniku do fantázie. Pozor na alkohol a lieky.'),
        ('moon', 'neptune', 'trine', 'positive',
         'Hlboká intuícia a duchovné vnímanie. Krásne umelecké inšpirácie. Empatia a súcit.'),
        ('moon', 'neptune', 'opposition', 'negative',
         'Emocionálna dezilúzia a zmätok vo vzťahoch. Nereálne očakávania. Sklamanie.'),
    ])

    # t.Mesiac - n.Pluto
    entries.extend([
        ('moon', 'pluto', 'conjunction', 'neutral',
         'Hlboké emocionálne prežívanie a intenzívne pocity. Transformácia emočných vzorcov. Tajomstvá vychádzajú na povrch.'),
        ('moon', 'pluto', 'sextile', 'positive',
         'Hlboké emocionálne porozumenie. Schopnosť transformovať negatívne pocity. Psychologický vhľad.'),
        ('moon', 'pluto', 'square', 'negative',
         'Intenzívne a posadnuté emócie. Žiarlivosť a manipulácia. Emocionálne mocenské hry.'),
        ('moon', 'pluto', 'trine', 'positive',
         'Pozitívna emocionálna regenerácia. Hlboké porozumenie sebe a iným. Liečivý vplyv.'),
        ('moon', 'pluto', 'opposition', 'negative',
         'Intenzívne emocionálne konfrontácie. Manipulatívne správanie v okolí. Hlboké emočné krízy.'),
    ])

    # ═══════════════════════════════════════════════════
    # TRANZITY MERKÚRA (t.Merkúr)
    # ═══════════════════════════════════════════════════

    # t.Merkúr - n.Slnko
    entries.extend([
        ('mercury', 'sun', 'conjunction', 'positive',
         'Výborný deň pre komunikáciu, rokovania a dôležité rozhovory. Jasné myslenie a sebavyjadrenie.'),
        ('mercury', 'sun', 'sextile', 'positive',
         'Plynulá komunikácia a mentálna čulosť. Dobré pre obchodné záležitosti.'),
        ('mercury', 'sun', 'square', 'negative',
         'Komunikačné problémy a nedorozumenia. Nervozita. Nepodpisujte dôležité zmluvy.'),
        ('mercury', 'sun', 'trine', 'positive',
         'Výborné mentálne schopnosti. Úspešné rokovania a prezentácie. Dobré pre štúdium.'),
        ('mercury', 'sun', 'opposition', 'negative',
         'Názorové konflikty s okolím. Nepochopenie. Odkladajte dôležité rozhodnutia.'),
    ])

    # t.Merkúr - n.Mesiac
    entries.extend([
        ('mercury', 'moon', 'conjunction', 'positive',
         'Schopnosť vyjadriť emócie slovami. Dobré pre písanie, denníky, emocionálne rozhovory.'),
        ('mercury', 'moon', 'sextile', 'positive',
         'Citlivá a empatická komunikácia. Dobré pre poradenstvo a pomoc iným.'),
        ('mercury', 'moon', 'square', 'negative',
         'Emocionálne skreslená komunikácia. Nedorozumenia v rodine. Nervozita a nepokoj.'),
        ('mercury', 'moon', 'trine', 'positive',
         'Harmónia medzi rozumom a citmi. Výborná intuícia. Empatické rozhovory.'),
        ('mercury', 'moon', 'opposition', 'negative',
         'Konflikty medzi rozumovým a emocionálnym prístupom. Hádky v rodine kvôli komunikácii.'),
    ])

    # t.Merkúr - n.Merkúr
    entries.extend([
        ('mercury', 'mercury', 'conjunction', 'positive',
         'Merkúrov návrat - mentálna obnova. Nové myšlienky a komunikačné príležitosti. Ideálne pre učenie.'),
        ('mercury', 'mercury', 'sextile', 'positive',
         'Plynulé myslenie a komunikácia. Dobré pre štúdium, písanie a obchodné rokovania.'),
        ('mercury', 'mercury', 'square', 'negative',
         'Mentálne napätie a stres. Komunikačné problémy. Pozor na chyby v dokumentoch.'),
        ('mercury', 'mercury', 'trine', 'positive',
         'Vynikajúce mentálne schopnosti. Ľahko sa učíte a komunikujete. Kreatívne myslenie.'),
        ('mercury', 'mercury', 'opposition', 'negative',
         'Rozdielne pohľady na veci spôsobujú napätie. Informačné preťaženie. Rozptýlenosť.'),
    ])

    # t.Merkúr - n.Venuša
    entries.extend([
        ('mercury', 'venus', 'conjunction', 'positive',
         'Príjemná komunikácia, diplomatickosť a šarm. Ľúbostné listy, komplimenty. Umelecká inšpirácia.'),
        ('mercury', 'venus', 'sextile', 'positive',
         'Spoločenská komunikácia a diplomatické schopnosti. Dobré pre umelecké projekty.'),
        ('mercury', 'venus', 'square', 'negative',
         'Povrchná komunikácia a ťažkosti vyjadriť city. Nerozhodnosť v záležitostiach srdca.'),
        ('mercury', 'venus', 'trine', 'positive',
         'Harmonická a krásna komunikácia. Umelecká tvorivosť. Diplomacia a šarm.'),
        ('mercury', 'venus', 'opposition', 'negative',
         'Ťažkosti vyjadriť lásku a náklonnosť slovami. Komunikačné nedorozumenia vo vzťahoch.'),
    ])

    # t.Merkúr - n.Mars
    entries.extend([
        ('mercury', 'mars', 'conjunction', 'neutral',
         'Ostrý jazyk a rýchle myslenie. Schopnosť hájiť svoje názory. Pozor na agresivitu v komunikácii.'),
        ('mercury', 'mars', 'sextile', 'positive',
         'Rozhodná a jasná komunikácia. Schopnosť presvedčiť ostatných. Mentálna energia.'),
        ('mercury', 'mars', 'square', 'negative',
         'Verbálne konflikty a hádky. Ostrý jazyk spôsobuje problémy. Netrpezlivosť v komunikácii.'),
        ('mercury', 'mars', 'trine', 'positive',
         'Dynamická a presvedčivá komunikácia. Odvaha vyjadriť sa. Úspešné debaty a rokovania.'),
        ('mercury', 'mars', 'opposition', 'negative',
         'Slovné potýčky a argumenty. Impulzívne vyjadrenia, ktoré ľutujete. Nervozita.'),
    ])

    # t.Merkúr - n.Jupiter
    entries.extend([
        ('mercury', 'jupiter', 'conjunction', 'positive',
         'Rozšírené myslenie a optimistická komunikácia. Veľké plány a vízie. Dobré pre vzdelávanie.'),
        ('mercury', 'jupiter', 'sextile', 'positive',
         'Pozitívne myslenie a príležitosti pre učenie. Dobré správy. Úspešné cestovanie.'),
        ('mercury', 'jupiter', 'square', 'negative',
         'Prehnané sľuby a nerealistické plány. Informačné preťaženie. Pozor na klebety.'),
        ('mercury', 'jupiter', 'trine', 'positive',
         'Výborné príležitosti pre komunikáciu a vzdelávanie. Optimistické myslenie. Dobré správy.'),
        ('mercury', 'jupiter', 'opposition', 'negative',
         'Prehnaný optimizmus v komunikácii. Sľuby, ktoré neviete splniť. Pozor na detaily.'),
    ])

    # t.Merkúr - n.Saturn
    entries.extend([
        ('mercury', 'saturn', 'conjunction', 'neutral',
         'Vážne myslenie a disciplinovaná komunikácia. Dobré pre plánovanie a organizáciu. Pesimistické myslenie.'),
        ('mercury', 'saturn', 'sextile', 'positive',
         'Praktické a organizované myslenie. Schopnosť koncentrácie. Dobré pre administratívu.'),
        ('mercury', 'saturn', 'square', 'negative',
         'Mentálne bloky a komunikačné bariéry. Pesimizmus a pochybnosti. Oneskorené správy.'),
        ('mercury', 'saturn', 'trine', 'positive',
         'Sústredené a hlboké myslenie. Praktické riešenia problémov. Múdre rozhodnutia.'),
        ('mercury', 'saturn', 'opposition', 'negative',
         'Kritika od okolia a komunikačné prekážky. Depresívne myslenie. Oneskorenia.'),
    ])

    # t.Merkúr - n.Urán
    entries.extend([
        ('mercury', 'uranus', 'conjunction', 'neutral',
         'Geniálne nápady a nekonvenčné myslenie. Nečakané správy. Prekvapivé informácie.'),
        ('mercury', 'uranus', 'sextile', 'positive',
         'Originálne myšlienky a inovatívne riešenia. Technologické príležitosti. Zaujímavé stretnutia.'),
        ('mercury', 'uranus', 'square', 'negative',
         'Nervozita a nesústredenosť. Nečakané problémy s technikou. Impulzívne rozhodnutia.'),
        ('mercury', 'uranus', 'trine', 'positive',
         'Brilantné nápady a technologické inovácie. Príjemné prekvapenia v komunikácii.'),
        ('mercury', 'uranus', 'opposition', 'negative',
         'Nečakané správy a narušenia plánov. Technické problémy. Komunikačný chaos.'),
    ])

    # t.Merkúr - n.Neptún
    entries.extend([
        ('mercury', 'neptune', 'conjunction', 'neutral',
         'Intuitívne myslenie a umelecká inšpirácia. Pozor na zmätok a nepresnosti v komunikácii.'),
        ('mercury', 'neptune', 'sextile', 'positive',
         'Poetická a inšpirovaná komunikácia. Výborné pre umeleckú tvorbu a meditáciu.'),
        ('mercury', 'neptune', 'square', 'negative',
         'Zmätená komunikácia a nedorozumenia. Klamstvo a podvod. Pozor na zmluvy a dohody.'),
        ('mercury', 'neptune', 'trine', 'positive',
         'Umelecká inšpirácia a intuitívne myslenie. Poetické vyjadrovanie. Duchovné porozumenie.'),
        ('mercury', 'neptune', 'opposition', 'negative',
         'Klamlivá komunikácia a zmätok. Nepočujte na fámy. Vyhnite sa podpisu zmlúv.'),
    ])

    # t.Merkúr - n.Pluto
    entries.extend([
        ('mercury', 'pluto', 'conjunction', 'neutral',
         'Hlboké a prenikavé myslenie. Schopnosť odhaliť tajomstvá. Intenzívna komunikácia.'),
        ('mercury', 'pluto', 'sextile', 'positive',
         'Prenikavá analýza a strategické myslenie. Schopnosť presvedčiť. Psychologický vhľad.'),
        ('mercury', 'pluto', 'square', 'negative',
         'Obsedantné myslenie a manipulatívna komunikácia. Verbálne mocenské hry. Paranoja.'),
        ('mercury', 'pluto', 'trine', 'positive',
         'Hlboké porozumenie a analytické schopnosti. Transformačné rozhovory. Odhaľovanie právd.'),
        ('mercury', 'pluto', 'opposition', 'negative',
         'Manipulatívna komunikácia od okolia. Tajomstvá a intrigy. Mocenské hry so slovami.'),
    ])

    # ═══════════════════════════════════════════════════
    # TRANZITY VENUŠE (t.Venuša)
    # ═══════════════════════════════════════════════════

    _venus_entries = {
        'sun': {
            'conjunction': ('positive', 'Zvýšená príťažlivosť, šarm a spoločenskosť. Krásny deň pre lásku a romantiku. Finančné príležitosti.'),
            'sextile': ('positive', 'Príjemné spoločenské kontakty. Harmónia vo vzťahoch. Dobré pre nakupovanie a investície.'),
            'square': ('negative', 'Lenivosť a túžba po pôžitkoch. Napätie vo vzťahoch. Prehnané míňanie peňazí.'),
            'trine': ('positive', 'Krásny deň pre lásku, umenie a spoločenské udalosti. Príjemné stretnutia a harmónia.'),
            'opposition': ('negative', 'Vzťahové napätie. Konflikty medzi osobnými potrebami a potrebami partnera.'),
        },
        'moon': {
            'conjunction': ('positive', 'Emocionálna neha a romantická nálada. Krása v domácnosti. Príjemné rodinné chvíle.'),
            'sextile': ('positive', 'Harmónia medzi citmi a vzťahmi. Príjemná nálada. Dobré pre dekorovanie domova.'),
            'square': ('negative', 'Emocionálna neistota v láske. Rozmaznanosť a precitlivelosť. Míňanie pre útechu.'),
            'trine': ('positive', 'Emocionálna harmónia a láska. Príjemné domáce prostredie. Romantické chvíle.'),
            'opposition': ('negative', 'Napätie medzi emocionálnymi potrebami a vzťahmi. Pocit, že nie ste milovaní dosť.'),
        },
        'mercury': {
            'conjunction': ('positive', 'Diplomatická a príjemná komunikácia. Ľúbostné správy. Umelecké vyjadrovanie.'),
            'sextile': ('positive', 'Ľahká a príjemná komunikácia. Dobré pre spoločenské udalosti a diplomaciu.'),
            'square': ('negative', 'Povrchná komunikácia. Ťažkosti vyjadriť city. Diplomatické chyby.'),
            'trine': ('positive', 'Harmonická a šarmantná komunikácia. Komplementy a pozitívne správy.'),
            'opposition': ('negative', 'Nedorozumenia vo vzťahoch. Ťažkosti vyjadriť lásku a ocenenie.'),
        },
        'venus': {
            'conjunction': ('positive', 'Venušin návrat - nový vzťahový a finančný cyklus. Zvýšená príťažlivosť a krása.'),
            'sextile': ('positive', 'Harmónia vo vzťahoch a finančná stabilita. Estetické pôžitky.'),
            'square': ('negative', 'Napätie vo vzťahoch a finančné ťažkosti. Nesúlad hodnôt.'),
            'trine': ('positive', 'Krásne obdobie pre lásku a umenie. Finančné príležitosti. Spoločenský úspech.'),
            'opposition': ('negative', 'Vzťahové konfrontácie. Prehodnotenie hodnôt a financií.'),
        },
        'mars': {
            'conjunction': ('positive', 'Vášnivá energia v láske a tvorivosti. Silná sexuálna príťažlivosť. Aktívna romantika.'),
            'sextile': ('positive', 'Harmonická sexuálna energia. Aktívna a príjemná romantika. Tvorivá činnosť.'),
            'square': ('negative', 'Napätie v láske a sexualite. Impulzívne míňanie. Hádky kvôli žiarlivosti.'),
            'trine': ('positive', 'Vášnivá a harmonická energia. Romantické dobrodružstvá. Umelecká tvorivosť.'),
            'opposition': ('negative', 'Vzťahové konflikty a žiarlivosť. Napätie medzi láskou a vášňou.'),
        },
        'jupiter': {
            'conjunction': ('positive', 'Štedrá a veľkorysá láska. Finančné príležitosti. Spoločenský úspech a popularita.'),
            'sextile': ('positive', 'Príjemné spoločenské príležitosti. Finančný rast. Harmonické vzťahy.'),
            'square': ('negative', 'Prehnaná rozmaznanosť a extravagancia. Prehnané míňanie na luxus.'),
            'trine': ('positive', 'Šťastie v láske a financiách. Veľkorysé príležitosti. Krásne spoločenské udalosti.'),
            'opposition': ('negative', 'Prehnaná láska k luxusu. Finančná nezodpovednosť. Vzťahová sýtosť.'),
        },
        'saturn': {
            'conjunction': ('negative', 'Vážnosť vo vzťahoch. Záväzky a zodpovednosť. Hodnotenie vzťahov. Emočný chlad.'),
            'sextile': ('positive', 'Stabilné a zrelé vzťahy. Praktické finančné rozhodnutia. Vernosť.'),
            'square': ('negative', 'Osameloisť a odmietnutie v láske. Finančné obmedzenia. Emočná strnulosť.'),
            'trine': ('positive', 'Stabilné a vytrvalé vzťahy. Finančná rozvážnosť. Zrelá láska.'),
            'opposition': ('negative', 'Vzťahové krízy a prehodnotenie záväzkov. Finančné ťažkosti.'),
        },
        'uranus': {
            'conjunction': ('neutral', 'Neočakávaná láska a prekvapenia vo vzťahoch. Nekonvenčná príťažlivosť.'),
            'sextile': ('positive', 'Vzrušujúce románce a nové priateľstvá. Originálny umelecký výraz.'),
            'square': ('negative', 'Náhle zmeny vo vzťahoch. Nestabilita v láske. Nepokojná túžba po slobode.'),
            'trine': ('positive', 'Osviežujúce romantické zážitky. Originalita v umení a láske. Vzrušenie.'),
            'opposition': ('negative', 'Nečakané vzťahové otrasy. Partner prekvapuje. Potreba slobody v láske.'),
        },
        'neptune': {
            'conjunction': ('neutral', 'Romantické ilúzie a idealizácia. Duchovná láska. Pozor na klam vo vzťahoch.'),
            'sextile': ('positive', 'Romantická a duchovná láska. Umelecká inšpirácia. Súcitné vzťahy.'),
            'square': ('negative', 'Ilúzie v láske. Podvod a sklamanie vo vzťahoch. Finančné straty cez podvod.'),
            'trine': ('positive', 'Duchovná a transcendentná láska. Umelecký génius. Bezpodmienečná láska.'),
            'opposition': ('negative', 'Dezilúzia a klam vo vzťahoch. Finančné podvody. Nerealistické očakávania od partnera.'),
        },
        'pluto': {
            'conjunction': ('neutral', 'Intenzívna a transformačná láska. Hlboká vášeň. Posadnutosť a žiarlivosť.'),
            'sextile': ('positive', 'Hlboká a transformačná láska. Finančná regenerácia. Magnetická príťažlivosť.'),
            'square': ('negative', 'Mocenské hry vo vzťahoch. Žiarlivosť a posadnutosť. Finančné krízy.'),
            'trine': ('positive', 'Hlboká transformácia vzťahov. Intenzívna a liečivá láska. Finančná regenerácia.'),
            'opposition': ('negative', 'Vzťahové mocenské boje. Intenzívne konflikty. Transformácia cez krízu.'),
        },
    }
    for natal, aspects in _venus_entries.items():
        for aspect, (effect, text) in aspects.items():
            entries.append(('venus', natal, aspect, effect, text))

    # ═══════════════════════════════════════════════════
    # TRANZITY MARSA (t.Mars)
    # ═══════════════════════════════════════════════════

    _mars_entries = {
        'sun': {
            'conjunction': ('neutral', 'Zvýšená energia, odvaha a iniciatíva. Silná vôľa. Pozor na impulzívnosť, hádky a nehody.'),
            'sextile': ('positive', 'Produktívna energia a iniciatíva. Úspešné presadzovanie záujmov. Šport a aktivita.'),
            'square': ('negative', 'Konflikty, agresivita a úrazy. Impulzívne konanie prináša problémy. Horúčkovité obdobie.'),
            'trine': ('positive', 'Silná energia a odhodlanie. Úspech v súťažiach a podnikoch. Výborné pre šport.'),
            'opposition': ('negative', 'Konfrontácie s autorami a rivalmi. Haštlivosť. Riziko úrazov a nehôd.'),
        },
        'moon': {
            'conjunction': ('neutral', 'Emocionálna výbušnosť a impulzívnosť. Vášnivé reakcie. Aktívna energia v domácnosti.'),
            'sextile': ('positive', 'Emocionálna odvaha a rozhodnosť. Aktívne riešenie domácich záležitostí.'),
            'square': ('negative', 'Emocionálne výbuchy a hádky doma. Podráždenosť. Konflikty s rodinou.'),
            'trine': ('positive', 'Odvaha čeliť emočným výzvam. Aktívna starostlivosť o rodinu a domov.'),
            'opposition': ('negative', 'Konflikty v rodinnom prostredí. Emocionálna agresivita. Netrpezlivosť.'),
        },
        'mercury': {
            'conjunction': ('neutral', 'Ostrý rozum a rýchle rozhodovanie. Verbálna agresivita. Pozor na ostré slová.'),
            'sextile': ('positive', 'Dynamická komunikácia a mentálna energia. Schopnosť obhájiť svoje názory.'),
            'square': ('negative', 'Slovné hádky a konflikty. Unáhlené rozhodnutia. Mentálny stres.'),
            'trine': ('positive', 'Presvedčivá komunikácia a rozhodné myslenie. Úspešné debaty.'),
            'opposition': ('negative', 'Verbálne útoky a obrana. Konflikty v komunikácii. Mentálna agresivita.'),
        },
        'venus': {
            'conjunction': ('positive', 'Vášnivá romantika a sexuálna príťažlivosť. Aktívna láska a tvorivosť.'),
            'sextile': ('positive', 'Harmonická sexuálna energia a aktívna romantika. Tvorivá činnosť.'),
            'square': ('negative', 'Sexuálne napätie a vzťahové konflikty. Žiarlivosť a impulzívne výdavky.'),
            'trine': ('positive', 'Vášnivá harmónia v láske. Aktívna tvorivosť. Erotická príťažlivosť.'),
            'opposition': ('negative', 'Konflikt medzi túžbou a láskou. Sexuálne frustrácie. Impulzívne vzťahy.'),
        },
        'mars': {
            'conjunction': ('neutral', 'Marsov návrat - nový cyklus energie a akcie. Zvýšená vitalita aj agresivita.'),
            'sextile': ('positive', 'Produktívna energia a sebavedomie. Úspech v športových a podnikateľských aktivitách.'),
            'square': ('negative', 'Frustrovaná energia a agresivita. Konflikty a nehody. Netrpezlivosť a hnev.'),
            'trine': ('positive', 'Výborná fyzická kondícia a energie. Úspech v súťažiach. Odvaha a rozhodnosť.'),
            'opposition': ('negative', 'Konfrontácie s rivalmi a nepriateľmi. Mocenské boje. Fyzické napätie.'),
        },
        'jupiter': {
            'conjunction': ('positive', 'Veľká energia pre expanziu a dobrodružstvo. Odvaha riskovať. Úspech v podnikoch.'),
            'sextile': ('positive', 'Šťastná akcia a úspešná iniciatíva. Podpora od vplyvných ľudí.'),
            'square': ('negative', 'Prehnané riskovanie a hazard. Konflikty kvôli presvedčeniu. Nestriedma energia.'),
            'trine': ('positive', 'Šťastná odvaha a úspešné dobrodružstvá. Expanzívna energia. Víťazstvo.'),
            'opposition': ('negative', 'Konflikty kvôli presvedčeniu a morálke. Prehnané riziko. Právne problémy.'),
        },
        'saturn': {
            'conjunction': ('negative', 'Blokovaná energia a frustrácia. Obmedzenia a prekážky. Potreba disciplíny a trpezlivosti.'),
            'sextile': ('positive', 'Disciplinovaná a kontrolovaná energia. Vytrvalá práca prináša výsledky.'),
            'square': ('negative', 'Veľká frustrácia a blokovaná akcia. Konflikty s autoritami. Fyzické ťažkosti.'),
            'trine': ('positive', 'Kontrolovaná sila a vytrvalosť. Disciplinovaná práca. Dlhodobé ciele.'),
            'opposition': ('negative', 'Konfrontácia s autoritami a obmedzeniami. Blokovaná energia. Hnev z frustrácie.'),
        },
        'uranus': {
            'conjunction': ('neutral', 'Náhla a neočakávaná akcia. Impulzívne rozhodnutia. Nehody z nepozornosti. Túžba po slobode.'),
            'sextile': ('positive', 'Originálna a inovatívna akcia. Nečakané príležitosti. Technologické inovácie.'),
            'square': ('negative', 'Výbušná a nepredvídateľná energia. Nehody, úrazy. Impulzívne a nebezpečné konanie.'),
            'trine': ('positive', 'Vzrušujúca a oslobodzujúca energia. Inovatívne akcie. Technologický pokrok.'),
            'opposition': ('negative', 'Náhle konfrontácie a nepredvídateľné udalosti. Nehody a úrazy. Chaotická energia.'),
        },
        'neptune': {
            'conjunction': ('neutral', 'Oslabená energia a zmätené akcie. Duchovný boj. Pozor na intoxikáciu a úniky.'),
            'sextile': ('positive', 'Inšpirovaná akcia pre duchovné a umelecké ciele. Súcitná energia.'),
            'square': ('negative', 'Oslabená vôľa a zmätená akcia. Podvod a klam. Energetické vyčerpanie.'),
            'trine': ('positive', 'Inšpirovaná a duchovná akcia. Umelecká tvorivosť. Súcitné konanie.'),
            'opposition': ('negative', 'Oslabená energia a dezilúzia. Podvod a manipulácia. Strata smeru.'),
        },
        'pluto': {
            'conjunction': ('neutral', 'Mocná a transformačná energia. Intenzívne konflikty alebo prielomy. Pozor na posadnutosť.'),
            'sextile': ('positive', 'Hlboká sila a transformačná energia. Schopnosť prekonať prekážky. Regenerácia.'),
            'square': ('negative', 'Intenzívne mocenské boje a konflikty. Deštruktívna energia. Nebezpečné situácie.'),
            'trine': ('positive', 'Mocná regeneračná sila. Transformácia cez akciu. Hlboká odvaha.'),
            'opposition': ('negative', 'Mocenské konfrontácie a intenzívne konflikty. Deštruktívne tendencie.'),
        },
    }
    for natal, aspects in _mars_entries.items():
        for aspect, (effect, text) in aspects.items():
            entries.append(('mars', natal, aspect, effect, text))

    # ═══════════════════════════════════════════════════
    # TRANZITY JUPITERA (t.Jupiter) - významné, trvajú týždne
    # ═══════════════════════════════════════════════════

    _jupiter_entries = {
        'sun': {
            'conjunction': ('positive', 'Výnimočné obdobie rastu, šťastia a príležitostí. Rozširovanie obzorov cestovaním, vzdelávaním alebo novými skúsenosťami. Zvýšená sebadôvera a optimizmus priťahujú pomoc a úspech.'),
            'sextile': ('positive', 'Príjemné príležitosti pre osobný rast. Podpora od nadriadených a mentorov. Cestovanie a vzdelávanie prinášajú radosť.'),
            'square': ('negative', 'Prehnaný optimizmus a nadmerná sebadôvera. Tendencie brať na seba príliš veľa záväzkov. Extravagancia a prejedanie. Právne komplikácie.'),
            'trine': ('positive', 'Najlepšie obdobie pre osobný rozvoj a kariérny postup. Šťastie a príležitosti prichádzajú ľahko. Cestovanie a filozofické rozšírenie horizontu.'),
            'opposition': ('negative', 'Konfrontácia s prehnaným sebavedomím. Iní vás konfrontujú s realitou. Pozor na prehnané sľuby a záväzky.'),
        },
        'moon': {
            'conjunction': ('positive', 'Emocionálna hojnosť a pocit šťastia. Rozšírenie domova alebo rodiny. Štedrť a pohostinnosť. Dobrá doba pre nehnuteľnosti.'),
            'sextile': ('positive', 'Emocionálna pohoda a optimizmus. Príjemné rodinné udalosti. Rozšírenie domáceho prostredia.'),
            'square': ('negative', 'Emocionálna nestriedmosť a prehnané reakcie. Ťažkosti s hmotnosťou. Rodinné konflikty kvôli prehnaným očakávaniam.'),
            'trine': ('positive', 'Hlboký pocit šťastia a emocionálneho bezpečia. Rodinné oslavy a stretnutia. Príjemné bývanie.'),
            'opposition': ('negative', 'Emocionálne preháňanie a ťažkosti s rovnováhou medzi osobnými potrebami a rodinou.'),
        },
        'mercury': {
            'conjunction': ('positive', 'Rozšírené myslenie a komunikačné schopnosti. Výborné pre vzdelávanie, publikovanie a cestovanie. Optimistické plány.'),
            'sextile': ('positive', 'Pozitívne myslenie a príležitosti pre vzdelávanie. Úspešné rokovania a publikácie.'),
            'square': ('negative', 'Prehnané sľuby a nerealistické plány. Informačné preťaženie. Chyby z nepozornosti. Právne problémy.'),
            'trine': ('positive', 'Brilantné myslenie a úspešná komunikácia. Výborné pre štúdium, publikovanie a obchodné rokovania.'),
            'opposition': ('negative', 'Názorové konflikty a prehnaná argumentácia. Ťažkosti s detailami. Nepresnosti.'),
        },
        'venus': {
            'conjunction': ('positive', 'Šťastie v láske a vzťahoch. Finančná hojnosť. Spoločenský úspech a popularita. Skvelé pre svadby a oslavy.'),
            'sextile': ('positive', 'Príjemné vzťahové a finančné príležitosti. Spoločenské udalosti a umenie.'),
            'square': ('negative', 'Prehnaný luxus a rozmaznanosť. Finančná extravagancia. Lenivosť vo vzťahoch.'),
            'trine': ('positive', 'Najlepšie obdobie pre lásku, financie a umenie. Šťastné vzťahy a spoločenský úspech.'),
            'opposition': ('negative', 'Prehnaná láska k luxusu a pôžitkom. Finančná nezodpovednosť. Partnerské napätie.'),
        },
        'mars': {
            'conjunction': ('positive', 'Obrovská energia a entuziazmus. Odvaha riskovať a expandovať. Úspech v podnikaní a športe.'),
            'sextile': ('positive', 'Úspešná iniciatíva a šťastná akcia. Podpora pre fyzické a podnikateľské aktivity.'),
            'square': ('negative', 'Prehnané riskovanie a agresívna expanzia. Právne problémy. Konflikty kvôli ideológii.'),
            'trine': ('positive', 'Šťastná odvaha a úspešné podnikanie. Expanzívna energia prináša úspechy.'),
            'opposition': ('negative', 'Konflikty kvôli presvedčeniu a morálke. Právne spory. Prehnané riziko.'),
        },
        'jupiter': {
            'conjunction': ('positive', 'Jupiterov návrat (každých 12 rokov) - nový cyklus rastu, šťastia a expanzie. Významné príležitosti.'),
            'sextile': ('positive', 'Harmonický rast a príležitosti. Filozofické rozšírenie horizontu. Cestovanie.'),
            'square': ('negative', 'Prehnané ambície a konflikt presvedčení. Právne komplikácie. Nesplniteľné sľuby.'),
            'trine': ('positive', 'Vynikajúce obdobie pre rast, cestovanie a vzdelávanie. Šťastné príležitosti.'),
            'opposition': ('negative', 'Konfrontácia s vlastnými presvedčeniami. Právne spory. Prehnané očakávania.'),
        },
        'saturn': {
            'conjunction': ('neutral', 'Dôležitý tranzit - rovnováha medzi expanziou a obmedením. Múdre rozhodnutia o raste. Realitický optimizmus.'),
            'sextile': ('positive', 'Vyvážený rast a disciplína. Finančná stabilita. Kariérny postup cez tvrdú prácu.'),
            'square': ('negative', 'Konflikt medzi rastom a obmedzeniami. Finančné ťažkosti. Pesimizmus blokuje príležitosti.'),
            'trine': ('positive', 'Harmonický rast v rámci stability. Kariérny postup. Finančné zabezpečenie.'),
            'opposition': ('negative', 'Konfrontácia medzi optimizmom a realitou. Ekonomické ťažkosti. Právne problémy.'),
        },
        'uranus': {
            'conjunction': ('positive', 'Nečakané šťastie a príležitosti. Oslobodzujúci rast. Dobrodružné cestovanie. Filosofická revolúcia.'),
            'sextile': ('positive', 'Inovatívne príležitosti a progresívny rast. Technologické a vedecké objavy.'),
            'square': ('negative', 'Napätie medzi tradíciou a pokrokom. Nečakané zmeny plánov. Nestabilita.'),
            'trine': ('positive', 'Vzrušujúce príležitosti pre nekonvenčný rast. Inovácie a objavy.'),
            'opposition': ('negative', 'Nečakané zmeny narúšajú plány na rast. Konflikty medzi slobodou a expanziou.'),
        },
        'neptune': {
            'conjunction': ('neutral', 'Duchovný rast a rozšírenie vedomia. Idealizmus a vízie. Pozor na klamlivé príležitosti.'),
            'sextile': ('positive', 'Duchovný a umelecký rast. Súcitné a filantropické aktivity. Inšpirácia.'),
            'square': ('negative', 'Klamlivé príležitosti a nerealistické plány. Duchovný zmätok. Finančné podvody.'),
            'trine': ('positive', 'Hlboký duchovný rast a filozofické porozumenie. Umelecká a mystická inšpirácia.'),
            'opposition': ('negative', 'Konfrontácia ideálov s realitou. Dezilúzia a sklamanie. Finančné straty.'),
        },
        'pluto': {
            'conjunction': ('neutral', 'Mocná transformácia a hlboký rast. Príležitosť pre zásadnú životnú zmenu. Intenzívny duchovný vývoj.'),
            'sextile': ('positive', 'Hlboká transformácia s podporou šťastia. Príležitosti pre obnovu a rast.'),
            'square': ('negative', 'Mocenské boje komplikujú rast. Etické dilémy. Intenzívne konflikty o presvedčenie.'),
            'trine': ('positive', 'Pozitívna hlboká transformácia. Mocný duchovný rast. Príležitosti pre obnovu.'),
            'opposition': ('negative', 'Konfrontácia s mocenskými štruktúrami. Transformačné krízy. Intenzívne konflikty.'),
        },
    }
    for natal, aspects in _jupiter_entries.items():
        for aspect, (effect, text) in aspects.items():
            entries.append(('jupiter', natal, aspect, effect, text))

    # ═══════════════════════════════════════════════════
    # TRANZITY SATURNA (t.Saturn) - karmické, trvajú týždne-mesiace
    # ═══════════════════════════════════════════════════

    _saturn_entries = {
        'sun': {
            'conjunction': ('negative', 'Vážne obdobie prehodnotenia životného smeru. Obmedzenia a zodpovednosti. Nízka vitalita, ale príležitosť pre dozretie. Starostlivosť o zdravie.'),
            'sextile': ('positive', 'Disciplinovaný pokrok a uznanie. Praktické výsledky a stabilita. Kariérny rast cez tvrdú prácu.'),
            'square': ('negative', 'Kritické obdobie osobného vývoja. Prekážky a frustrácia. Konflikty s autoritami. Nízka energia. Potreba prehodnotenia cieľov.'),
            'trine': ('positive', 'Stabilný pokrok a zodpovedný rast. Uznanie za vykonanú prácu. Kariérny postup. Disciplína prináša výsledky.'),
            'opposition': ('negative', 'Konfrontácia s realitou a zodpovednosťou. Vzťahové výzvy. Zdravotné ťažkosti. Čas na rozhodnutia pre budúcnosť.'),
        },
        'moon': {
            'conjunction': ('negative', 'Emocionálna tiaž a melanchólia. Pocit izolácie. Rodinné zodpovednosti. Obmedzenia v domácnosti.'),
            'sextile': ('positive', 'Emocionálna stabilita a zrelosť. Praktické riešenia domácich záležitostí. Vnútorná sila.'),
            'square': ('negative', 'Depresívna nálada a emocionálne obmedzenia. Rodinné konflikty. Pocit osamelosti.'),
            'trine': ('positive', 'Emocionálna múdrosť a stabilita. Pokojné riešenie rodinných záležitostí. Vnútorný mier.'),
            'opposition': ('negative', 'Emočný chlad a izolácia. Rodinné krízy. Konfrontácia s emocionálnymi vzorcami.'),
        },
        'mercury': {
            'conjunction': ('neutral', 'Vážne a hlboké myslenie. Koncentrácia a disciplína. Pesimistické myšlienky. Dôležité rozhodnutia.'),
            'sextile': ('positive', 'Sústredené a disciplinované myslenie. Praktické riešenia problémov. Organizačné schopnosti.'),
            'square': ('negative', 'Mentálne bloky a komunikačné ťažkosti. Pesimistické myslenie. Oneskorenia v komunikácii.'),
            'trine': ('positive', 'Hlboké a múdre myslenie. Praktické plánovanie. Organizačný talent.'),
            'opposition': ('negative', 'Kritika a negatívna komunikácia. Mentálny tlak. Pesimistické názory okolia.'),
        },
        'venus': {
            'conjunction': ('negative', 'Obmedzenia vo vzťahoch a financiách. Osameloisť alebo vážne záväzky. Hodnotenie vzťahov. Emočný chlad.'),
            'sextile': ('positive', 'Stabilné a vážne vzťahy. Finančná disciplína. Dlhodobé investície.'),
            'square': ('negative', 'Vzťahové krízy a finančné ťažkosti. Odmietnutie a osameloisť. Emočná strnulosť.'),
            'trine': ('positive', 'Zrelé a stabilné vzťahy. Finančná zodpovednosť. Trvalé hodnoty.'),
            'opposition': ('negative', 'Vzťahové konfrontácie a rozchody. Finančné obmedzenia. Prehodnotenie hodnôt.'),
        },
        'mars': {
            'conjunction': ('negative', 'Blokovaná energia a frustrácia. Potreba disciplíny a trpezlivosti. Fyzické obmedzenia. Tvrdá práca.'),
            'sextile': ('positive', 'Disciplinovaná energia a vytrvalá práca. Kontrolovaná sila. Dlhodobé ciele.'),
            'square': ('negative', 'Veľká frustrácia a blokovaná akcia. Konflikty s autoritami. Hnev a bezmocnosť. Fyzické ťažkosti.'),
            'trine': ('positive', 'Kontrolovaná a vytrvalá sila. Úspech v dlhodobých projektoch. Fyzická výdrž.'),
            'opposition': ('negative', 'Konfrontácie s autoritami a obmedzeniami. Mocenské boje. Fyzické vyčerpanie.'),
        },
        'jupiter': {
            'conjunction': ('neutral', 'Rovnováha medzi expanziou a disciplínou. Realistické plánovanie. Zodpovedný rast.'),
            'sextile': ('positive', 'Harmonické spojenie rastu a disciplíny. Praktický optimizmus. Stabilný pokrok.'),
            'square': ('negative', 'Konflikt medzi expanziou a obmedzeniami. Finančné ťažkosti. Pesimizmus versus optimizmus.'),
            'trine': ('positive', 'Vyvážený a stabilný rast. Múdre investície. Kariérny postup.'),
            'opposition': ('negative', 'Konfrontácia medzi rastom a obmedzeniami. Ekonomické výzvy. Prehodnotenie cieľov.'),
        },
        'saturn': {
            'conjunction': ('negative', 'Saturnov návrat (každých 29 rokov) - zásadné životné míľniky. Prehodnotenie celého života. Dozrievanie a zodpovednosť. Konce a nové začiatky.'),
            'sextile': ('positive', 'Období konsolidácie a stability. Praktické výsledky dlhodobej práce. Uznanie.'),
            'square': ('negative', 'Karmické výzvy a krízy. Potreba zásadných zmien v štruktúre života. Ťažké rozhodnutia.'),
            'trine': ('positive', 'Obdobie stability a dozrievania. Plody dlhodobej práce. Vnútorný mier a múdrosť.'),
            'opposition': ('negative', 'Konfrontácia s karmickými lekciami. Životné krízy a prehodnotenie. Dôležité rozhodnutia.'),
        },
        'uranus': {
            'conjunction': ('negative', 'Napätie medzi tradíciou a zmenou. Narušenie štruktúr. Potreba prispôsobenia novej realite.'),
            'sextile': ('positive', 'Praktická integrácia zmien. Inovácie v rámci existujúcich štruktúr. Progresívna disciplína.'),
            'square': ('negative', 'Intenzívny konflikt medzi stabilitou a zmenou. Nečakané narušenie štruktúr. Stres a napätie.'),
            'trine': ('positive', 'Harmonická integrácia nového a starého. Inovatívne štruktúry. Progresívna stabilita.'),
            'opposition': ('negative', 'Konfrontácia medzi starým a novým poriadkom. Rušivé zmeny. Adaptácia pod tlakom.'),
        },
        'neptune': {
            'conjunction': ('negative', 'Rozklad štruktúr a zmätok. Strata istôt. Duchovné hľadanie. Potreba nových základov.'),
            'sextile': ('positive', 'Duchovná disciplína a praktická spiritualita. Kreatívne štruktúry.'),
            'square': ('negative', 'Rozklad a zmätok v štruktúrach. Strata orientácie. Podvod a klam. Existenčné pochybnosti.'),
            'trine': ('positive', 'Harmónia medzi praktikou a ideálmi. Duchovná zrelosť. Umelecká disciplína.'),
            'opposition': ('negative', 'Konfrontácia reality a ilúzií. Rozčarovanie. Strata štruktúr.'),
        },
        'pluto': {
            'conjunction': ('negative', 'Hlboká transformácia životných štruktúr. Zásadné zmeny v kariére a zodpovednostiach. Koniec starého a začiatok nového.'),
            'sextile': ('positive', 'Konštruktívna transformácia. Posilnenie štruktúr. Hlboká disciplína a obnova.'),
            'square': ('negative', 'Intenzívna deštrukcia starých štruktúr. Mocenské boje v kariére. Karmické krízy.'),
            'trine': ('positive', 'Mocná a pozitívna transformácia. Posilnenie životných štruktúr. Hlboká obnova.'),
            'opposition': ('negative', 'Konfrontácia s mocenskými štruktúrami. Transformačné krízy v kariére.'),
        },
    }
    for natal, aspects in _saturn_entries.items():
        for aspect, (effect, text) in aspects.items():
            entries.append(('saturn', natal, aspect, effect, text))

    # ═══════════════════════════════════════════════════
    # TRANZITY URÁNU (t.Urán) - revolučné, trvajú mesiace
    # ═══════════════════════════════════════════════════

    _uranus_entries = {
        'sun': {
            'conjunction': ('neutral', 'Zásadná životná zmena a oslobodenie. Objavenie pravého ja. Neočakávané udalosti menia životný smer. Potreba autenticity.'),
            'sextile': ('positive', 'Vzrušujúce príležitosti pre osobný rast. Originálne projekty. Nové priateľstvá s nekonvenčnými ľuďmi.'),
            'square': ('negative', 'Intenzívne napätie a náhle zmeny. Nepokoje a rebélia. Nečakané krízy. Potreba slobody za každú cenu.'),
            'trine': ('positive', 'Pozitívne a vzrušujúce životné zmeny. Objavenie nových talentov. Oslobodzujúci osobný rast.'),
            'opposition': ('negative', 'Nečakané konfrontácie a životné otrasy. Iní ľudia prinášajú chaos. Vzťahové zmeny.'),
        },
        'moon': {
            'conjunction': ('neutral', 'Emocionálna revolúcia a oslobodenie. Nečakané zmeny v domácnosti a rodine. Potreba emocionálnej slobody.'),
            'sextile': ('positive', 'Osviežujúce emočné zážitky. Nové domáce usporiadanie. Zaujímavé rodinné udalosti.'),
            'square': ('negative', 'Emocionálna nestabilita a náhle zmeny nálad. Narušenie domáceho pokoja. Rodinné konflikty.'),
            'trine': ('positive', 'Pozitívne emocionálne zmeny a oslobodenie od starých vzorcov. Nové bývanie alebo domáce usporiadanie.'),
            'opposition': ('negative', 'Emocionálne šoky od najbližších. Nečakané rodinné udalosti. Nestabilita doma.'),
        },
        'mercury': {
            'conjunction': ('neutral', 'Revolučné myšlienky a nečakané informácie. Geniálne nápady. Zmena spôsobu myslenia.'),
            'sextile': ('positive', 'Originálne a inovatívne myslenie. Technologické príležitosti. Zaujímavé stretnutia.'),
            'square': ('negative', 'Mentálne napätie a nečakané zmeny plánov. Technické problémy. Nervozita.'),
            'trine': ('positive', 'Brilantné nápady a technologický pokrok. Originálna komunikácia. Inovácie.'),
            'opposition': ('negative', 'Nečakané správy a komunikačný chaos. Technologické zlyhania. Dezorientácia.'),
        },
        'venus': {
            'conjunction': ('neutral', 'Neočakávaná láska alebo zmena vo vzťahu. Nekonvenčná príťažlivosť. Finančné prekvapenia.'),
            'sextile': ('positive', 'Vzrušujúce românce a nové priateľstvá. Nekonvenčné umenie. Nečakané finančné príležitosti.'),
            'square': ('negative', 'Náhle vzťahové zmeny a rozchody. Finančná nestabilita. Impulzívne vzťahy.'),
            'trine': ('positive', 'Osviežujúce a vzrušujúce vzťahové zážitky. Umelecká originalita. Finančné inovácie.'),
            'opposition': ('negative', 'Nečakané vzťahové otrasy. Partner prekvapuje nepríjemne. Finančné šoky.'),
        },
        'mars': {
            'conjunction': ('neutral', 'Podráždenosť, netrpezlivosť, náhle nehody.'),
            'sextile': ('positive', 'Inovatívna energia a originálna akcia. Technologické projekty. Nečakané príležitosti pre akciu.'),
            'square': ('negative', 'Výbušná energia a nehody. Impulzívne a nebezpečné konanie. Konflikty a rebélia.'),
            'trine': ('positive', 'Vzrušujúca a inovatívna energia. Technologické prielomy. Odvaha k originálnym krokom.'),
            'opposition': ('negative', 'Nečakané konflikty a výbušné situácie. Nehody z nepozornosti. Chaotická energia.'),
        },
        'jupiter': {
            'conjunction': ('positive', 'Nečakané šťastie a príležitosti. Oslobodzujúca expanzia. Dobrodružné cestovanie.'),
            'sextile': ('positive', 'Progresívne príležitosti pre rast. Inovatívne filozofické myslenie. Technologický pokrok.'),
            'square': ('negative', 'Napätie medzi tradíciou a pokrokom. Nečakané zmeny plánov. Nestabilný rast.'),
            'trine': ('positive', 'Vzrušujúce príležitosti pre rast a objavovanie. Progresívne ideály sa realizujú.'),
            'opposition': ('negative', 'Konflikty medzi slobodou a expanziou. Nečakané zmeny ruinujú plány.'),
        },
        'saturn': {
            'conjunction': ('negative', 'Napätie medzi slobodou a zodpovednosťou. Narušenie existujúcich štruktúr. Potreba adaptácie.'),
            'sextile': ('positive', 'Praktická integrácia zmien do existujúcich štruktúr. Inovatívna disciplína.'),
            'square': ('negative', 'Intenzívny konflikt medzi starou a novou cestou. Nečakané narušenie stability. Kríza.'),
            'trine': ('positive', 'Harmonická integrácia zmien. Inovatívne štruktúry. Stabilný pokrok.'),
            'opposition': ('negative', 'Konfrontácia medzi tradíciou a revolúciou. Nútené zmeny. Adaptačná kríza.'),
        },
        'uranus': {
            'conjunction': ('neutral', 'Uránov návrat (okolo 84 rokov) - zásadná životná transformácia a oslobodenie. Vek múdrosti.'),
            'sextile': ('positive', 'Harmonické zmeny a inovácie. Príjemné prekvapenia. Progresívny osobný rast.'),
            'square': ('negative', 'Životná kríza a náhle zmeny smeru (okolo 21 a 63 rokov). Rebélia a nestabilita.'),
            'trine': ('positive', 'Plynulé životné zmeny a pozitívna evolúcia. Naplnenie originality.'),
            'opposition': ('negative', 'Stredná životná kríza (okolo 42 rokov). Konfrontácia s nesplnenými snami. Potreba zmeny.'),
        },
        'neptune': {
            'conjunction': ('neutral', 'Duchovná revolúcia a rozpúšťanie hraníc. Mystické zážitky. Zmätok aj osvietenie.'),
            'sextile': ('positive', 'Duchovné prebudenie a intuitívne inovácie. Umelecká originalita.'),
            'square': ('negative', 'Zmätok medzi ilúziou a realitou. Duchovný chaos. Dezilúzia a nestabilita.'),
            'trine': ('positive', 'Harmónia medzi inováciou a duchovnosťou. Intuitívne prielomy.'),
            'opposition': ('negative', 'Konfrontácia medzi slobodou a ilúziami. Duchovné krízy. Zmätok.'),
        },
        'pluto': {
            'conjunction': ('neutral', 'Mocná revolúcia a hlboká transformácia. Zásadné životné zmeny. Oslobodenie od mocenských štruktúr.'),
            'sextile': ('positive', 'Konštruktívna revolúcia a transformácia. Inovatívna obnova. Progresívna moc.'),
            'square': ('negative', 'Intenzívny konflikt medzi slobodou a mocou. Revolučné krízy. Deštruktívne zmeny.'),
            'trine': ('positive', 'Mocná a oslobodzujúca transformácia. Hlboké inovácie. Progresívna obnova spoločnosti.'),
            'opposition': ('negative', 'Konfrontácia medzi slobodou a kontrolou. Mocenské revolúcie. Intenzívne krízy.'),
        },
    }
    for natal, aspects in _uranus_entries.items():
        for aspect, (effect, text) in aspects.items():
            entries.append(('uranus', natal, aspect, effect, text))

    # ═══════════════════════════════════════════════════
    # TRANZITY NEPTÚNA (t.Neptún) - duchovné, trvajú mesiace-roky
    # ═══════════════════════════════════════════════════

    _neptune_entries = {
        'sun': {
            'conjunction': ('neutral', 'Hlboká duchovná transformácia. Rozpúšťanie ega a starých identít. Zvýšená citlivosť a intuícia. Riziko zmätku a straty identity. Pozor na alkohol a lieky.'),
            'sextile': ('positive', 'Duchovný rast a umelecká inšpirácia. Zvýšená empatia a súcit. Príležitosti pre duchovný rozvoj.'),
            'square': ('negative', 'Zmätok identity a strata smeru. Klam a dezilúzia. Energetické vyčerpanie. Problémy s návykovými látkami.'),
            'trine': ('positive', 'Harmonická duchovná evolúcia. Umelecká tvorivosť na vysokej úrovni. Hlboká intuícia a múdrosť.'),
            'opposition': ('negative', 'Dezilúzia vo vzťahoch a konfrontácia s klamom. Strata energie. Potreba nájsť svoju pravdu.'),
        },
        'moon': {
            'conjunction': ('neutral', 'Extrémna emocionálna citlivosť a psychická otviorenosť. Rozmazanie hraníc medzi vlastnými a cudzími emóciami. Duchovná hlbka.'),
            'sextile': ('positive', 'Hlboká intuícia a empatia. Duchovné emocionálne zážitky. Umelecká citlivosť.'),
            'square': ('negative', 'Emocionálny zmätok a precitlivenosť. Nereálne emocionálne vzorce. Závislosťi pre útechu.'),
            'trine': ('positive', 'Duchovná emocionálna hĺbka. Bezpodmienečná láska a súcit. Umelecká citlivosť.'),
            'opposition': ('negative', 'Emocionálna dezilúzia a klam v blízkych vzťahoch. Strata emocionálneho zakotvenia.'),
        },
        'mercury': {
            'conjunction': ('neutral', 'Intuitívne a imaginatívne myslenie. Umelecká inšpirácia. Pozor na zmätok a nepresnosti v komunikácii.'),
            'sextile': ('positive', 'Poetická a intuitívna komunikácia. Umelecké písanie. Duchovné porozumenie.'),
            'square': ('negative', 'Mentálny zmätok a nepresné myslenie. Klamstvá a nedorozumenia. Pozor na podvod.'),
            'trine': ('positive', 'Intuitívne a umelecké myslenie. Poetická komunikácia. Duchovná múdrosť.'),
            'opposition': ('negative', 'Klamlivá komunikácia a mentálny zmätok. Podvod v obchode. Nepresné informácie.'),
        },
        'venus': {
            'conjunction': ('neutral', 'Idealizácia lásky a krásy. Duchovná láska. Umelecká inšpirácia. Pozor na klam a ilúzie vo vzťahoch.'),
            'sextile': ('positive', 'Romantická a duchovná láska. Umelecká tvorivosť. Súcitné vzťahy.'),
            'square': ('negative', 'Ilúzie v láske a financiách. Podvod a sklamanie. Závislosť na vzťahoch.'),
            'trine': ('positive', 'Transcendentná a duchovná láska. Umelecký génius. Bezpodmienečná láska.'),
            'opposition': ('negative', 'Dezilúzia a klam vo vzťahoch. Finančné straty cez podvod. Nereálne očakávania.'),
        },
        'mars': {
            'conjunction': ('negative', 'Oslabená vôľa a zmätená akcia. Energetické vyčerpanie. Pozor na intoxikáciu a tajné aktivity.'),
            'sextile': ('positive', 'Inšpirovaná akcia pre duchovné ciele. Súcitná energia. Umelecká tvorivosť.'),
            'square': ('negative', 'Oslabená energia a motivácia. Podvod a klamlivé aktivity. Pozor na alkohol a drogy.'),
            'trine': ('positive', 'Inšpirovaná a duchovná akcia. Umelecká energia. Súcitné konanie.'),
            'opposition': ('negative', 'Oslabenie a dezilúzia v aktivitách. Tajní nepriatelia. Energetické vyčerpanie.'),
        },
        'jupiter': {
            'conjunction': ('positive', 'Hlboký duchovný rast a expanzia vedomia. Mystické zážitky. Idealizmus a filantropiá.'),
            'sextile': ('positive', 'Duchovný a filozofický rast. Charitatívne aktivity. Umelecké úspechy.'),
            'square': ('negative', 'Duchovný zmätok a klamlivé príležitosti. Prehnaný idealizmus. Finančné straty.'),
            'trine': ('positive', 'Hlboký duchovný rast a mystické porozumenie. Umelecká a filozofická inšpirácia.'),
            'opposition': ('negative', 'Konfrontácia ideálov s realitou. Dezilúzia z viery a filozofie.'),
        },
        'saturn': {
            'conjunction': ('negative', 'Rozpúšťanie starých štruktúr a istôt. Existenčná kríza. Strata orientácie. Duchovné hľadanie.'),
            'sextile': ('positive', 'Praktická spiritualita. Disciplinovaný duchovný rast. Kreatívne štruktúry.'),
            'square': ('negative', 'Rozklad životných štruktúr a zmätok. Dezilúzia z autority. Existenčný strach.'),
            'trine': ('positive', 'Harmonická integrácia duchovnosti do praktického života. Kreatívna disciplína.'),
            'opposition': ('negative', 'Konfrontácia reality s ilúziami. Rozčarovanie z autority. Strata štruktúr.'),
        },
        'uranus': {
            'conjunction': ('neutral', 'Duchovné prebudenie a revolúcia vedomia. Mystické a paranormálne zážitky. Rozmazanie reality.'),
            'sextile': ('positive', 'Intuitívne prielomy a duchovné inovácie. Originálna mystika. Technologická spiritualita.'),
            'square': ('negative', 'Duchovný chaos a zmätok. Konfúzia medzi víziami a realitou. Nestabilita.'),
            'trine': ('positive', 'Harmonická duchovná evolúcia a intuitívne inovácie. Mystický pokrok.'),
            'opposition': ('negative', 'Konfrontácia medzi slobodou a ilúziami. Duchovné krízy a zmätok.'),
        },
        'neptune': {
            'conjunction': ('neutral', 'Neptúnov návrat (okolo 165 rokov) - generačný aspekt. Duchovná kulminacia.'),
            'sextile': ('positive', 'Duchovná harmónia a mystická inšpirácia. Hlboká intuícia a súcit.'),
            'square': ('negative', 'Duchovná kríza a dezilúzia. Zmätok a strata viery. Potreba nového duchovného smeru.'),
            'trine': ('positive', 'Hlboká duchovná harmónia. Mystická múdrosť a umelecká inšpirácia.'),
            'opposition': ('negative', 'Duchovná konfrontácia a prehodnotenie ideálov. Dezilúzia.'),
        },
        'pluto': {
            'conjunction': ('neutral', 'Hlboká duchovná transformácia. Rozpad ilúzií a obnova na hlbšej úrovni. Mystická smrť a znovuzrodenie.'),
            'sextile': ('positive', 'Duchovná regenerácia a transformácia. Hlboké mystické porozumenie. Liečenie.'),
            'square': ('negative', 'Intenzívna duchovná kríza. Konfrontácia s temnotou a strachmi. Rozklad ilúzií.'),
            'trine': ('positive', 'Mocná duchovná transformácia a hlboké liečenie. Mystická regenerácia.'),
            'opposition': ('negative', 'Konfrontácia duchovnosti s mocou. Intenzívne mystické krízy.'),
        },
    }
    for natal, aspects in _neptune_entries.items():
        for aspect, (effect, text) in aspects.items():
            entries.append(('neptune', natal, aspect, effect, text))

    # ═══════════════════════════════════════════════════
    # TRANZITY PLUTA (t.Pluto) - transformačné, trvajú roky
    # ═══════════════════════════════════════════════════

    _pluto_entries = {
        'sun': {
            'conjunction': ('neutral', 'Zásadná životná transformácia. Konfrontácia s hlbokými pravdami o sebe. Koniec starého ja a zrodenie nového. Mocenské krízy alebo veľká vnútorná sila.'),
            'sextile': ('positive', 'Pozitívna osobná transformácia. Hlboké sebapznanie. Príležitosti pre obnovu a posilnenie.'),
            'square': ('negative', 'Intenzívne mocenské boje a životné krízy. Potreba nechať odísť staré. Konfrontácia s tieňovou stránkou.'),
            'trine': ('positive', 'Mocná a pozitívna osobná transformácia. Hlboká sebadôvera a vnútorná sila. Regenerácia.'),
            'opposition': ('negative', 'Intenzívne vzťahové konfrontácie a mocenské boje. Transformácia cez krízy s inými ľuďmi.'),
        },
        'moon': {
            'conjunction': ('neutral', 'Hlboká emocionálna transformácia. Intenzívne pocity a podvedomé vzorce vychádzajú na povrch. Rodinné krízy.'),
            'sextile': ('positive', 'Hlboké emocionálne porozumenie a liečenie. Transformácia rodinných vzorcov. Psychologický vhľad.'),
            'square': ('negative', 'Intenzívne emocionálne krízy a posadnutosť. Manipulácia v rodine. Hlboké strachy.'),
            'trine': ('positive', 'Pozitívna emocionálna regenerácia. Liečenie hlbokých rán. Psychologická sila.'),
            'opposition': ('negative', 'Emocionálne konfrontácie a mocenské hry v rodine. Intenzívne krízy.'),
        },
        'mercury': {
            'conjunction': ('neutral', 'Prenikavé a transformačné myslenie. Odhalovanie tajomstiev a právd. Intenzívna komunikácia.'),
            'sextile': ('positive', 'Hlboká analytická schopnosť. Strategické myslenie. Psychologický vhľad v komunikácii.'),
            'square': ('negative', 'Obsedantné myslenie a paranoja. Manipulatívna komunikácia. Verbálne mocenské hry.'),
            'trine': ('positive', 'Prenikavá inteligencia a analytické schopnosti. Transformačná komunikácia.'),
            'opposition': ('negative', 'Mocenské hry v komunikácii. Tajomstvá a intrigy. Manipulácia informáciami.'),
        },
        'venus': {
            'conjunction': ('neutral', 'Intenzívna a transformačná láska. Hlboká vášeň a posadnutosť. Finančná transformácia.'),
            'sextile': ('positive', 'Hlboká a transformačná láska. Finančná regenerácia. Magnetická príťažlivosť.'),
            'square': ('negative', 'Mocenské hry vo vzťahoch. Žiarlivosť a posadnutosť. Finančné krízy a dlhy.'),
            'trine': ('positive', 'Intenzívna a liečivá láska. Hlboká transformácia vzťahov. Finančná obnova.'),
            'opposition': ('negative', 'Vzťahové mocenské boje a intenzívne konflikty. Finančné krízy.'),
        },
        'mars': {
            'conjunction': ('neutral', 'Obrovská a intenzívna energia. Mocné akcie a konflikty. Pozor na nebezpečné situácie a posadnutosť.'),
            'sextile': ('positive', 'Mocná a kontrolovaná energia. Strategická akcia. Schopnosť prekonať akékoľvek prekážky.'),
            'square': ('negative', 'Deštruktívna energia a intenzívne konflikty. Nebezpečné situácie. Mocenské boje.'),
            'trine': ('positive', 'Obrovská sila a vytrvalosť. Strategická akcia prináša zásadné zmeny.'),
            'opposition': ('negative', 'Intenzívne konfrontácie a mocenské boje. Deštruktívna energia. Nebezpečenstvo.'),
        },
        'jupiter': {
            'conjunction': ('positive', 'Mocná transformácia prináša rast a šťastie. Hlboké duchovné prielomy. Zásadné životné príležitosti.'),
            'sextile': ('positive', 'Konštruktívna transformácia a pozitívny rast. Filosofická hĺbka. Príležitosti.'),
            'square': ('negative', 'Mocenské boje komplikujú rast. Etické dilémy. Intenzívne konflikty o hodnoty.'),
            'trine': ('positive', 'Pozitívna hlboká transformácia s expanziou. Duchovný rast a materializácia príležitostí.'),
            'opposition': ('negative', 'Konfrontácia rastu s hlbokými zmenami. Mocenské konflikty komplikujú plány.'),
        },
        'saturn': {
            'conjunction': ('negative', 'Hlboká transformácia životných štruktúr a kariéry. Koniec starého poriadku. Karmické lekcie.'),
            'sextile': ('positive', 'Konštruktívna transformácia štruktúr. Posilnenie disciplíny a zodpovednosti.'),
            'square': ('negative', 'Intenzívna deštrukcia starých štruktúr. Kariérne krízy. Mocenské boje s autoritami.'),
            'trine': ('positive', 'Mocná a pozitívna obnova životných štruktúr. Hlboká disciplína a transformácia.'),
            'opposition': ('negative', 'Konfrontácia s mocenskými štruktúrami. Kariérne krízy a transformácia.'),
        },
        'uranus': {
            'conjunction': ('neutral', 'Revolučná transformácia spoločnosti a osobného života. Zásadné zmeny. Oslobodenie od hlbokých väzieb.'),
            'sextile': ('positive', 'Inovatívna transformácia. Progresívne zmeny. Technologická revolúcia.'),
            'square': ('negative', 'Intenzívne krízy medzi slobodou a mocou. Revolučné konflikty. Deštruktívne zmeny.'),
            'trine': ('positive', 'Mocná a oslobodzujúca transformácia. Progresívna obnova spoločnosti.'),
            'opposition': ('negative', 'Konfrontácia slobody s mocou. Revolučné krízy a intenzívne konflikty.'),
        },
        'neptune': {
            'conjunction': ('neutral', 'Hlboká mystická transformácia. Rozpad ilúzií a obnova na hlbšej duchovnej úrovni.'),
            'sextile': ('positive', 'Duchovná regenerácia a hlboké liečenie. Mystická transformácia. Hlboký súcit.'),
            'square': ('negative', 'Intenzívna duchovná kríza. Konfrontácia s temnotou. Rozklad ilúzií.'),
            'trine': ('positive', 'Mocná duchovná transformácia a hlboké liečenie. Mystická regenerácia vedomia.'),
            'opposition': ('negative', 'Konfrontácia duchovnosti s mocou. Mystické krízy a transformácia.'),
        },
        'pluto': {
            'conjunction': ('neutral', 'Plutov návrat (okolo 248 rokov) - generačný aspekt. Zásadná kolektívna transformácia.'),
            'sextile': ('positive', 'Harmonická hlboká transformácia. Posilnenie vnútornej sily. Regenerácia.'),
            'square': ('negative', 'Životná kríza a zásadná transformácia (okolo 62 rokov). Mocenské konflikty. Koniec éry.'),
            'trine': ('positive', 'Pozitívna hlboká obnova a transformácia. Vnútorná sila a múdrosť.'),
            'opposition': ('negative', 'Konfrontácia s vlastnou tieňovou stránkou. Hlboká kríza a transformácia (okolo 124 rokov).'),
        },
    }
    for natal, aspects in _pluto_entries.items():
        for aspect, (effect, text) in aspects.items():
            entries.append(('pluto', natal, aspect, effect, text))

    return entries


# Export all transit data
TRANSIT_DATA = _build_transit_entries()
