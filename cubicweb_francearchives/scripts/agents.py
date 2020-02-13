# -*- coding: utf-8 -*-
"""
L'extraction de ces données est basée sur les règles issues de la
norme de nommage des agents RDA :

1/ Les *noms* et les *prénoms* sont indiqués avant d’éventuels
   parenthèses. Les noms sont séparés des prénoms par une virgule.

2/ La partie entre parenthèses peut contenir les
   information ci-dessous, séparés par « ; » , dans l’ordre suivant :

 - Dates d’existence (format année – mois – jour ou année-année).
 - Profession/occupation.
 - Dates d’activités.
 - Titre (abbé,juriste…).
 - Autre (lieu d’exercice par exemple).

Il est à noter que si la règle sur les *noms* et les *prénoms*, assez
simple, semble être respectée pour la plupart des données, c'est bien
moins souvent le cas pour la seconde règle (en particulier pour le
séparateur, souvent « , »  à la place de « ; » ).
"""


from pprint import pprint

import re

import unittest

import csv

label_dates_rgx = re.compile(
    r"(?P<lastname>.*?)\s*,\s*(?P<firstname>.*?)\s*\(\s*(?P<infos>.*?)\s*\)"
)
label_rgx = re.compile(r"(?P<lastname>.*)\s*,\s*(?P<firstname>.*?)$")

dates_occupation_rgx = re.compile(
    r"\s*(?P<dates>.*[\d|\.|\?]{1,4}.*)\s*[,;]\s*(?P<occupation>.*)\s*$"
)

occupation_dates_rgx = re.compile(
    r"\s*(?P<occupation>.*)\s*[,;]\s*(?P<dates>.*[\d|\.|\?]{1,4}.*)\s*$"
)

interval_rgx = re.compile(
    r"(?P<start>[^-]*[\d|\.|\?]{1,4})?\s*[-|]*\s*(?P<end>[^-]*[\d|\.|\?]{1,4})?$",
    flags=re.IGNORECASE | re.UNICODE,
)

year_rgx = re.compile(r"([\d|\.|\?]{2,4})", flags=re.IGNORECASE | re.UNICODE)

literal_date_rgx = re.compile(
    r"\d+\s+(jan[\.\w]*|fév[\.\w]*|mar[\.\w]*|avr[\.\w]*|mai|jun|juin|jui[\.\w]*"
    r"|aoû[\.\w]*|aou[\.\w]*|ao[\.\w]*|sep[\.\w]*|oct[\.\w]*"
    r"|nov[\.\w]*|déc[\.\w]*)\s+(\d+)$",
    flags=re.IGNORECASE | re.UNICODE,
)


def process_dates_results(match):
    if match:
        res = match.groupdict()
        for key, value in list(res.items()):
            extracted = ""
            if value:
                for rgx, group in (
                    (literal_date_rgx, 2),
                    (year_rgx, 1),
                ):
                    m = rgx.match(value)
                    if m:
                        extracted = m.group(group)
                        break
            res[key] = extracted
        if any(res.values()):
            return res
    return {}


def parse_date_range(infos):
    """
    >>>  parse_date_range('12-121')
    {'start': '12', 'end': '121')
    >>>  parse_date_range('1223')
    {'start': '1223', 'end': ''}
    >>>  parse_date_range('12?-342')
    {'start': '12?', 'end': '342'}
    >>>  parse_date_range('12.-11??')
    {'start': '12.', 'end': '11??'}
    """
    return process_dates_results(interval_rgx.search(infos))


def parse_date_range_occupation(infos):
    """Allen, Henry Tureman (1859-1930 ; militaire)"""
    res = {}
    _rgx = dates_occupation_rgx
    match = _rgx.search(infos)
    if match:
        res = match.groupdict()
        dates = res.pop("dates")
        if dates:
            res.update(parse_date_range(dates.strip()))
        # keep birth and death dates
        if res.get("start") or res.get("end"):
            return res
    _rgx = occupation_dates_rgx
    match = _rgx.search(infos)
    if match:
        res = match.groupdict()
        dates = res.pop("dates")
        if dates:
            res.update(parse_date_range(dates.strip()))
        # remove activity dates
        res.pop("start", None)
        res.pop("end", None)
    return res


def process_info(infos):
    res = parse_date_range_occupation(infos)
    if res:
        return res
    res = parse_date_range(infos)
    if res:
        return res
    return {"occupation": infos}


def extract_label(label):
    match = label_dates_rgx.search(label)
    if match:
        infos = match.groupdict()
        infos.update(process_info(infos["infos"]))
        return infos
    match = label_rgx.search(label)
    if match:
        return match.groupdict()
    return {}


def extract_agentlabels(cnx):
    batch_size = 100000
    cursor = cnx.cnxset.cu
    cursor.execute(
        """SELECT DISTINCT cw_agentauthority.cw_eid,cw_agentauthority.cw_label
        FROM cw_agentauthority JOIN cw_agentname
        ON cw_agentname.cw_authority=cw_agentauthority.cw_eid
        WHERE cw_agentname.cw_type='persname' ORDER BY cw_agentauthority.cw_label ASC"""
    )
    while True:
        rset = cursor.fetchmany(batch_size)
        if not rset:
            break
        yield [(eid, label, extract_label(label)) for eid, label in rset]


def towiki(infos):
    start = infos.get("start", "")
    end = infos.get("end", "")
    if start >= end or len(start) > len(end):
        start, end = "", ""
    return {
        "exteid": infos["eid"],
        "label": infos["label"],
        "nom": infos.get("lastname", "")[:126],
        "prenoms": infos.get("firstname", "")[:126],
        "date naissance": start,
        "date mort": end,
        "discipline 1": infos.get("occupation", "")[:126],
    }


def align(cnx):
    for i, agents in enumerate(extract_agentlabels(cnx)):
        processed_agents = []
        print("writing batch {i} ({n} agents)".format(i=i, n=len(agents)))
        headers = ["eid", "label", "lastname", "firstname", "infos", "start", "end", "occupation"]
        with open("/tmp/agents_{i}.csv".format(i=str(i).zfill(3)), "w") as outf:
            writer = csv.DictWriter(outf, fieldnames=headers, delimiter="\t")  # \t')
            writer.writerow(dict((fn, fn) for fn in writer.fieldnames))
            for eid, label, infos in agents:
                # if infos.get('infos'):
                infos = {k: v.encode("utf8") for k, v in list(infos.items())}
                infos.update({"eid": eid, "label": label.encode("utf8")})
                processed_agents.append(infos)
                writer.writerow(infos)
        headers = [
            "exteid",
            "label",
            "nom",
            "prenoms",
            "date naissance",
            "date mort",
            "discipline 1",
            "discipline 2",
            "discipline 3",
            "discipline 4",
        ]
        with open("/tmp/wikiagent_{i}.csv".format(i=str(i).zfill(3)), "w") as outf:
            writer = csv.DictWriter(outf, fieldnames=headers, delimiter="\t")  # \t')
            writer.writerow(dict((fn, fn) for fn in writer.fieldnames))
            for info in processed_agents:
                writer.writerow(towiki(info))


class Tests(unittest.TestCase):
    def assertInfos(self, label, infos):
        pprint(extract_label(label))
        self.assertDictEqual(extract_label(label), infos)

    def test_extract_label(self):
        ai = self.assertInfos
        ai(
            "Huquier, Jacques Gabriel (1730-1805)",
            {
                "infos": "1730-1805",
                "end": "1805",
                "start": "1730",
                "lastname": "Huquier",
                "firstname": "Jacques Gabriel",
            },
        )
        ai("Huquier, Jacques Gabriel", {"lastname": "Huquier", "firstname": "Jacques Gabriel"})
        ai(
            "Huquier, Jacques Gabriel (1730)",
            {
                "infos": "1730",
                "start": "1730",
                "end": "",
                "lastname": "Huquier",
                "firstname": "Jacques Gabriel",
            },
        )
        ai(
            "Allen, Henry Tureman (1859-1930 ; militaire)",
            {
                "firstname": "Henry Tureman",
                "infos": "1859-1930 ; militaire",
                "lastname": "Allen",
                "start": "1859",
                "end": "1930",
                "occupation": "militaire",
            },
        )
        ai(
            "Achard de Joumard de Léger, Marie Henriette (17..?-1787)",
            {
                "firstname": "Marie Henriette",
                "lastname": "Achard de Joumard de L\xc3\xa9ger",
                "infos": "17..?-1787",
                "end": "1787",
                "start": "17..",
            },
        )
        ai(
            "Achard, François (notaire à La Chapelle-Blanche-Saint-Martin, 1685-1690)",
            {
                "firstname": "François",
                "lastname": "Achard",
                "infos": "notaire à La Chapelle-Blanche-Saint-Martin, 1685-1690",
                "occupation": "notaire à La Chapelle-Blanche-Saint-Martin",
            },
        ),
        ai(
            "Jablonowska, Marie Louise (1701?-1773)",
            {
                "firstname": "Marie Louise",
                "lastname": "Jablonowska",
                "infos": "1701?-1773",
                "start": "1701",
                "end": "1773",
            },
        )
        ai(
            "Lloyd George, David (Earl of Dwyfor) (1863-1945 ; juriste et homme politique britannique)",  # noqa
            {
                "firstname": "David",
                "infos": "Earl of Dwyfor",
                "lastname": "Lloyd George",
                "occupation": "Earl of Dwyfor",
            },
        )
        ai(
            "Lloyd George, David (1863-1945 ; juriste et homme politique britannique)",  # noqa
            {
                "firstname": "David",
                "infos": "1863-1945 ; juriste et homme politique britannique",
                "lastname": "Lloyd George",
                "start": "1863",
                "end": "1945",
                "occupation": "juriste et homme politique britannique",
            },
        )
        ai(
            "Allezon, Jean (notaire à Beaumont-en-Véron, 6 janvier 1663-14 août 1678)",
            {
                "firstname": "Jean",
                "lastname": "Allezon",
                "occupation": "notaire à Beaumont-en-Véron",
                "infos": "notaire à Beaumont-en-Véron, 6 janvier 1663-14 août 1678",
            },
        )
        ai(
            "La Tremblais (de), Jean Nazaire Louis (notaire à Preuilly-sur-Claise, 20 avril 1817-19 novembre 1837)",  # noqa
            {
                "firstname": "Jean Nazaire Louis",
                "lastname": "La Tremblais (de)",
                "occupation": "notaire à Preuilly-sur-Claise",
                "infos": "notaire à Preuilly-sur-Claise, 20 avril 1817-19 novembre 1837",
            },
        )
        ai(
            "Rigal, Bernard (1865-....)",
            {
                "end": "....",
                "firstname": "Bernard",
                "infos": "1865-....",
                "lastname": "Rigal",
                "start": "1865",
            },
        )
        ai(
            "LA BARE, Pierre de, sieur du Buron, P (1651)",
            {
                "end": "",
                "firstname": "Pierre de, sieur du Buron, P",
                "infos": "1651",
                "lastname": "LA BARE",
                "start": "1651",
            },
        )
        ai(
            "Labay de Viella, Louis Henri de (1764-1840)",
            {
                "end": "1840",
                "firstname": "Louis Henri de",
                "infos": "1764-1840",
                "lastname": "Labay de Viella",
                "start": "1764",
            },
        )
        ai(
            "Labbé, Marguerite (veuve de Jacques Bigot)",
            {
                "firstname": "Marguerite",
                "infos": "veuve de Jacques Bigot",
                "lastname": "Labbé",
                "occupation": "veuve de Jacques Bigot",
            },
        )
        ai(
            "Labellie, Jean (1920-... ; peintre)",
            {
                "end": "...",
                "firstname": "Jean",
                "infos": "1920-... ; peintre",
                "lastname": "Labellie",
                "occupation": "peintre",
                "start": "1920",
            },
        )
        ai(
            "Labellie, Jean (1920-.... ; peintre) -- Sainte-Thérèse, église (Le Rouget, Cantal, France) -- 1945-1990",  # noqa
            {
                "end": "....",
                "firstname": "Jean",
                "infos": "1920-.... ; peintre",
                "lastname": "Labellie",
                "occupation": "peintre",
                "start": "1920",
            },
        )
        ai(
            "Labbé, Jean (actif en 1709-1747)",
            {
                "end": "1747",
                "firstname": "Jean",
                "infos": "actif en 1709-1747",
                "lastname": "Labbé",
                "start": "",
            },
        )

    def assertDateRange(self, info, res):
        self.assertDictEqual(parse_date_range(info), res)

    def test_parse_dates_range(self):
        dr = self.assertDateRange
        dr("1223", {"start": "1223", "end": ""})
        dr("-1223", {"start": "", "end": "1223"})
        dr("12-121", {"start": "12", "end": "121"})
        dr("1859-1930", {"start": "1859", "end": "1930"})
        dr("12?-342", {"start": "12?", "end": "342"})
        dr("12.-11??", {"start": "12.", "end": "11??"})
        dr("-", {})
        dr("20 avril 1817-19 novembre 1837", {"start": "1817", "end": "1837"})
        dr("6 décembre 1663-14 août 1678", {"start": "1663", "end": "1678"})
        dr("actif en 1709-1747", {"end": "1747", "start": ""})

    def assertOccupation(self, info, res):
        self.assertDictEqual(parse_date_range_occupation(info), res)

    def test_parse_occupation(self):
        oc = self.assertOccupation
        oc("1859-1930 ; militaire", {"start": "1859", "end": "1930", "occupation": "militaire"})


if __name__ == "__main__":
    align(cnx)  # noqa
