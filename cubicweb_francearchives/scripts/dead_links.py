# standard library imports
import csv
import sys
import logging
import subprocess
import os.path

SCHEME = "https"
NETLOC = "francearchives.fr"


def run_linkchecker(url, output_linkchecker, config=""):
    """Run linkchecker.

    :param str url: URL
    :param str output_linkchecker: linkchecker output file path

    :raises RuntimeError: if linkchecker is not executed successfully
    """
    args = ["linkchecker", url, "-F", "csv/utf_8/{}".format(output_linkchecker)]
    if config:
        args.append("--config={}".format(config))
    process = subprocess.Popen(args, stderr=subprocess.PIPE, text=True)
    _, err = process.communicate()
    return_code = process.wait()
    if return_code != 0:
        err = ":{err}".format(err=err) if err else ""
        raise RuntimeError("an error occurred while executing linkchecker{err}".format(err=err))


def read_in(linkchecker_path):
    """Read CSV file in.

    :param str linkchecker_path: path

    :returns: rows
    :rtype: list
    """
    with open(linkchecker_path) as fp:
        reader = csv.DictReader(filter(lambda row: not row.startswith("#"), fp), delimiter=";")
        rows = [row for row in reader]
    return rows


def clean_up_linkchecker(output_linkchecker, output_dead_links):
    """Clean LinkChecker up.

    :param str output_linkchecker: linkchecker output file path
    :param str output_dead_links: find-dead-links output file path
    """
    rows = read_in(output_linkchecker)
    rows = [[row["url"], row["parentname"], row["result"]] for row in rows]
    rows.insert(0, ["url", "url_parent", "result"])
    with open(os.path.join(output_dead_links, "liens_morts.csv"), "w") as fp:
        writer = csv.writer(fp, delimiter=";")
        writer.writerows(rows)


def main():
    """Main routine."""
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    linkchecker_path = os.path.join("/tmp", "linkchecker-out.csv")
    try:
        run_linkchecker(sys.argv[1], linkchecker_path)
    except RuntimeError as exception:
        logger.warning("incomplete results:%s", str(exception))
    clean_up_linkchecker(linkchecker_path, os.path.normpath(sys.argv[2]))


if __name__ == "__main__":
    main()
