"""EAD file parsing."""

# standard library imports
import csv
import sys
import os
import os.path

# third party imports
import lxml.etree

# library-specific imports


def parse(filepath):
    """Parse XML filepath.

    :param str filepath_: XML file
    """
    try:
        fp = open(filepath)
    except UnicodeError as exception:
        try:
            print("UnicodeError ({}) in XML file {}".format(exception, filepath))
        except UnicodeError as exception:
            print("UnicodeError ({})".format(exception))
        finally:
            fp.close()
            return
    try:
        tree = lxml.etree.parse(fp)
    except lxml.etree.LxmlError as exception:
        try:
            print("LxmlError ({}) in XML file {}".format(exception, filepath))
        except UnicodeError as exception:
            print("UnicodeError ({})".format(exception))
        fp.close()
        return
    except Exception as exception:
        try:
            print("Error ({}) in XML file {}".format(exception, filepath))
        except UnicodeError as exception:
            print("UnicodeError ({})".format(exception))
        fp.close()
        return
    root = tree.getroot()
    for tag in ("genreform", "occupation", "function"):
        try:
            rows = []
            for node in root.findall(".//{}".format(tag)):
                ancestors = lxml.etree.AncestorsIterator(node)
                rows.append(
                    (
                        filepath,
                        node.text,
                        next(ancestors).tag,
                        next(ancestors).tag,
                        next(ancestors).tag,
                    )
                )
            csvfile = open("{}.csv".format(tag), "a")
            csvwriter = csv.writer(csvfile)
            csvwriter.writerows(rows)
        except lxml.etree.LxmlError as exception:
            try:
                print("LxmlError ({}) in XML file {}".format(exception, filepath))
            except UnicodeError as exception:
                print("UnicodeError ({})".format(exception))
        except Exception as exception:
            try:
                print("Error ({}) in XML file {}".format(exception, filepath))
            except UnicodeError as exception:
                print("UnicodeError ({})".format(exception))
    fp.close()


def read_in(path):
    """Read XML files in.

    :param str path: path
    """
    print("# {}\n".format(path).upper())
    for filepath in os.listdir(path):
        filepath = "{}/{}".format(path, filepath)
        # print("-> parse {}".format(filepath))
        if os.path.isdir(filepath):
            read_in(filepath)
        else:
            if filepath.endswith(".xml"):
                parse(filepath)


def main(path):
    """Main routine.

    :param str path: path
    """
    read_in(path)


if __name__ == "__main__":
    path = sys.argv[1]
    main(path)
