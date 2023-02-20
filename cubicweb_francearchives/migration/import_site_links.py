import csv
import os.path as osp

""" import site links"""
HERE = osp.join(osp.abspath(osp.dirname(__file__)))


def datapath(relpath):
    return osp.join(HERE, "initialdata", relpath)


def import_site_links(cnx):
    cnx.execute("DELETE SiteLink X")
    cnx.commit()
    with open(datapath("SiteLinks.csv")) as f:
        reader = csv.reader(f, delimiter=",")
        header = next(reader)  # noqa
        for idx, row in enumerate(reader):
            if not any(row):
                continue
            if not all(row[:4]):
                print(f"skip line {idx} : {row}")
                continue
            kwargs = dict(
                ((key, value.strip()) for key, value in zip(header, row) if value and value.strip())
            )
            if not cnx.find("SiteLink", **kwargs):
                cnx.create_entity("SiteLink", **kwargs)


if __name__ == "__main__":
    import_site_links(cnx)  # noqa
