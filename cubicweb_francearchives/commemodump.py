# -*- coding: utf-8 -*-
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2020
# Contact http://www.logilab.fr -- mailto:contact@logilab.fr
#
# This software is governed by the CeCILL-C license under French law and
# abiding by the rules of distribution of free software. You can use,
# modify and/ or redistribute the software under the terms of the CeCILL-C
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty and the software's author, the holder of the
# economic rights, and the successive licensors have only limited liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading, using, modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean that it is complicated to manipulate, and that also
# therefore means that it is reserved for developers and experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systemsand/or
# data to be ensured and, more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL-C license and that you accept its terms.


# standard library imports
import os.path
import subprocess
import zipfile

# third party imports
# CubicWeb specific imports
# library specific imports


TABLE_NAMES = [
    "public.commemo_dates_dump",
    "public.commemo_images_dump",
    "public.commemo_programm_files_dump",
    "public.commemo_agent_dump",
    "public.commemo_dump",
    "public.commemo_dump_csv",
    "public.commemo_collection_images_dump",
    "public.commemo_collection_dump",
    "public.commemo_programm_dump",
]


def create_tables(cnx):
    cnx.system_sql(
        """-- create data for collections
        CREATE TABLE IF NOT EXISTS public.commemo_collection_dump AS (
            SELECT co.cw_eid AS collection_eid,
            co.cw_title AS title,
            co.cw_content AS content,
            co.cw_subtitle AS subtitle,
            co.cw_name AS name,
            co.cw_short_description AS description,
            co.cw_year AS year,
            co.cw_order AS display_order,
            co.cw_creation_date AS creation_date,
            co.cw_modification_date AS modification_date,
            NULL AS uri
            FROM published.cw_commemocollection co
        );

        ALTER TABLE public.commemo_collection_dump ADD PRIMARY KEY (collection_eid);
        ALTER TABLE public.commemo_collection_dump REPLICA IDENTITY FULL;

        -- create data for collection images
        CREATE TABLE IF NOT EXISTS public.commemo_collection_images_dump (
            collection_eid integer REFERENCES public.commemo_collection_dump(collection_eid),
            file_eid integer,
            caption text,
            description text,
            copyright text,
            file text
        );

        ALTER TABLE public.commemo_collection_images_dump
        ADD PRIMARY KEY(collection_eid, file_eid);

        INSERT INTO public.commemo_collection_images_dump
        SELECT co.cw_eid AS collection_eid,
        cw_image.cw_eid AS file_eid,
        cw_image.cw_caption AS caption,
        cw_image.cw_description AS description,
        cw_image.cw_copyright AS copyright,
        encode(cw_file.cw_data, 'escape') AS file
        FROM published.cw_commemocollection co
        LEFT JOIN section_image_relation ON co.cw_eid=eid_from
        LEFT JOIN cw_image ON cw_image.cw_eid=eid_to
        LEFT JOIN cw_file ON cw_file.cw_eid=cw_image.cw_image_file
        WHERE cw_image.cw_eid IS NOT NULL;

        -- create data for programms
        CREATE TABLE IF NOT EXISTS public.commemo_programm_dump AS (
            SELECT DISTINCT bc.cw_eid AS programm_eid,
            bc.cw_title AS title,
            bc.cw_content AS content,
            bc.cw_keywords AS keywords,
            bc.cw_description AS description,
            bc.cw_creation_date AS creation_date,
            bc.cw_modification_date AS modification_date
            FROM cw_basecontent bc
            LEFT JOIN published.cw_commemorationitem ci ON ci.cw_manif_prog=bc.cw_eid
            WHERE ci.cw_eid IS NOT NULL
        );

        ALTER TABLE public.commemo_programm_dump ADD PRIMARY KEY (programm_eid);

        -- create table for programm files
        CREATE TABLE IF NOT EXISTS public.commemo_programm_files_dump AS (
            SELECT cw_file.cw_eid AS programm_file_eid,
            bc.cw_eid AS programm_eid,
            encode(cw_file.cw_data, 'escape') AS file
            FROM cw_file JOIN referenced_files_relation f_rel ON cw_file.cw_eid = f_rel.eid_to
            JOIN cw_basecontent bc ON f_rel.eid_from = bc.cw_eid
            WHERE bc.cw_eid IN (SELECT ci.cw_manif_prog FROM published.cw_commemorationitem ci)
        );

        ALTER TABLE public.commemo_programm_files_dump ADD FOREIGN KEY(programm_eid)
        REFERENCES public.commemo_programm_dump(programm_eid);

        -- create data for commemorations --
        CREATE TABLE IF NOT EXISTS public.commemo_dump (
            commemo_eid integer PRIMARY KEY,
            title text,
            subtitle text,
            content text,
            year integer,
            collection_year integer,
            order_in_collection integer,
            collection_eid integer REFERENCES public.commemo_collection_dump(collection_eid),
            programm_eid integer REFERENCES public.commemo_programm_dump(programm_eid),
            keywords text,
            authors text,
            creation_date timestamp with time zone,
            modification_date timestamp with time zone,
            uri text
        );

        INSERT INTO public.commemo_dump
        SELECT ci.cw_eid AS commemo_eid,
        ci.cw_title AS title,
        ci.cw_subtitle AS subtitle,
        ci.cw_content AS content,
        ci.cw_year AS year,
        ci.cw_commemoration_year AS collection_year,
        ci.cw_order AS order_in_collection,
        ci.cw_collection_top AS collection_eid,
        ci.cw_manif_prog AS programm_eid,
        meta.cw_keywords,
        meta.cw_creator as authors,
        ci.cw_creation_date AS creation_date,
        ci.cw_modification_date AS modification_date,
        NULL AS uri
        FROM published.cw_commemorationitem ci
        LEFT JOIN cw_metadata meta ON ci.cw_metadata=meta.cw_eid;

        -- create data for commemoration info --
        CREATE TABLE IF NOT EXISTS public.commemo_dump_csv (
            commemo_eid integer  PRIMARY KEY,
            title text,
            subtitle text,
            file text,
            year integer,
            collection_year integer,
            order_in_collection integer,
            collection_eid integer REFERENCES public.commemo_collection_dump(collection_eid),
            programm_eid integer REFERENCES public.commemo_programm_dump(programm_eid),
            keywords text,
            authors text,
            creation_date timestamp with time zone,
            modification_date timestamp with time zone,
            uri text
        );

        INSERT INTO public.commemo_dump_csv
        SELECT ci.cw_eid AS commemo_eid,
        ci.cw_title AS title,
        ci.cw_subtitle AS subtitle,
        NULL AS file_eid,
        ci.cw_year AS year,
        ci.cw_commemoration_year AS collection_year,
        ci.cw_order AS order_in_collection,
        ci.cw_collection_top AS collection_eid,
        ci.cw_manif_prog AS programm_eid,
        meta.cw_keywords,
        meta.cw_creator as authors,
        ci.cw_creation_date AS creation_date,
        ci.cw_modification_date AS modification_date,
        NULL AS uri
        FROM published.cw_commemorationitem ci
        LEFT JOIN cw_metadata meta ON ci.cw_metadata=meta.cw_eid;


        -- create data for images --
        CREATE TABLE public.commemo_images_dump (
            commemo_eid integer REFERENCES public.commemo_dump(commemo_eid),
            file_eid integer,
            caption text,
            description text,
            copyright text,
            file text
        );

        ALTER TABLE public.commemo_images_dump ADD PRIMARY KEY (commemo_eid, file_eid);

        INSERT into public.commemo_images_dump
        SELECT ci.cw_eid AS commemo_eid,
        image.cw_eid AS file_eid,
        image.cw_caption AS caption,
        image.cw_description AS description,
        image.cw_copyright AS copyright,
        encode(f_image.cw_data, 'escape') AS file
        FROM published.cw_commemorationitem ci
        LEFT JOIN commemoration_image_relation image_rel ON ci.cw_eid=image_rel.eid_from
        LEFT JOIN cw_image image ON image_rel.eid_to = image.cw_eid
        LEFT JOIN cw_file f_image ON f_image.cw_eid = image.cw_image_file
        WHERE image.cw_eid IS NOT NULL;

        -- create data for dates --
        CREATE TABLE public.commemo_dates_dump (
            commemo_eid integer REFERENCES public.commemo_dump(commemo_eid),
            eid integer NOT NULL,
            event character varying(256),
            date date,
            cw_date_is_precise boolean
        );

        ALTER TABLE public.commemo_dates_dump ADD PRIMARY KEY (commemo_eid, eid);

        INSERT INTO public.commemo_dates_dump
        SELECT ci.cw_eid AS commemo_eid,
        d.cw_eid AS eid,
        d.cw_type AS event,
        d.cw_date AS date,
        d.cw_date_is_precise
        FROM cw_commemodate d
        LEFT JOIN commemo_dates_relation dc_rel ON dc_rel.eid_to=d.cw_eid
        LEFT JOIN published.cw_commemorationitem ci ON dc_rel.eid_from=ci.cw_eid
        WHERE d.cw_eid IS NOT NULL AND ci.cw_eid IS NOT NULL;

        -- create agents for commemos --
        CREATE TABLE public.commemo_agent_dump (
            commemo_eid integer REFERENCES public.commemo_dump(commemo_eid),
            label text,
            type character varying(256)
        );

        INSERT INTO public.commemo_agent_dump
        SELECT ci.cw_eid AS commemo_eid,
        agent.cw_label AS label,
        'agent'
        FROM published.cw_commemorationitem ci
        LEFT JOIN related_authority_relation auth_rel ON ci.cw_eid=auth_rel.eid_from
        LEFT JOIN cw_agentauthority agent ON auth_rel.eid_to = agent.cw_eid
        WHERE agent.cw_eid IS NOT NULL;

        INSERT INTO public.commemo_agent_dump
        SELECT ci.cw_eid AS commemo_eid,
        subject.cw_label AS label,
        'subject'
        FROM published.cw_commemorationitem ci
        LEFT JOIN related_authority_relation auth_rel ON ci.cw_eid=auth_rel.eid_from
        LEFT JOIN cw_subjectauthority subject ON auth_rel.eid_to = subject.cw_eid
        WHERE subject.cw_eid IS NOT NULL;

        INSERT INTO public.commemo_agent_dump
        SELECT ci.cw_eid AS commemo_eid,
        loc.cw_label AS label,
        'location'
        FROM published.cw_commemorationitem ci
        LEFT JOIN related_authority_relation auth_rel ON ci.cw_eid=auth_rel.eid_from
        LEFT JOIN cw_locationauthority loc ON auth_rel.eid_to = loc.cw_eid
        WHERE loc.cw_eid IS NOT NULL;"""
    )


def delete_tables(cnx):
    """Drop tables used for exporting commemoration data.

    :param Connection cnx: CubicWeb database connection
    """
    cnx.system_sql("".join("DROP TABLE IF EXISTS {};".format(table) for table in TABLE_NAMES))


def update_uris(cnx):
    """Update URIs.

    :param Connection cnx: CubicWeb database connection
    """
    for table, prefix in (
        ("public.commemo_dump", "commemo"),
        ("public.commemo_collection_dump", "collection"),
    ):
        cnx.cnxset.cu.executemany(
            "UPDATE {} SET uri=%s WHERE {}_eid=%s".format(table, prefix),
            [
                (cnx.entity_from_eid(eid).absolute_url(), eid)
                for eid, in cnx.system_sql("SELECT {}_eid FROM {}".format(prefix, table)).fetchall()
            ],
        )


def update_files(cnx, output_dir):
    """Update content files.

    :param Connection cnx: CubicWeb database connection
    :param str output_dir: output_directory basename
    """
    rows = cnx.system_sql("SELECT commemo_eid, coalesce(content, '') FROM public.commemo_dump")
    basename = os.path.join(output_dir, "commemo_content_{}.txt")
    disknames = []
    for eid, content in rows:
        diskname = basename.format(eid)
        with open(diskname, "w") as fp:
            fp.write(content)
        disknames.append((diskname, eid))
    cnx.cnxset.cu.executemany(
        "UPDATE public.commemo_dump_csv SET file=%s WHERE commemo_eid=%s", disknames
    )


def make_archive(archive, filenames):
    """Create Zip archive.

    :param str archive: path of Zip archive
    :param list filenames: list of diskname-arcname tuples
    """
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as fp:
        for diskname, arcname in set(filenames):  # remove duplicates
            if os.path.isdir(diskname):  # directory, we need to iterate over content
                for root, _, files in os.walk(diskname):
                    for file in files:
                        fp.write(os.path.join(root, file), arcname=os.path.join(arcname, file))
                continue
            fp.write(diskname, arcname)
        # add  README
        for filename, arcname in (("readme_commemodump.md", "README.md"),):
            fp.write(
                os.path.join(os.path.dirname(os.path.realpath(__file__)), "static", filename),
                arcname=arcname,
            )


def run_pg_dump(cnx, table, directory):
    """Dump table into directory-format archive. The output directory
    must not exist.

    :param Connection cnx: CubicWeb database connection
    :param str table: name of table or regex matching multiple tables
    :param str directory: name of directory to dump into

    :raises Exception: if dumping table failed
    """
    system_source_config = cnx.repo.config.system_source_config
    host = "@{}".format(
        system_source_config["db-host"] if system_source_config["db-host"] else "localhost"
    )
    port = ":{}".format(system_source_config["db-port"]) if system_source_config["db-port"] else ""
    password = (
        ":{}".format(system_source_config["db-password"])
        if system_source_config["db-password"]
        else ""
    )
    dbname = "postgresql://{user}{password}{host}{port}/{name}".format(
        user=system_source_config["db-user"],
        password=password,
        host=host,
        port=port,
        name=system_source_config["db-name"],
    )
    process = subprocess.Popen(
        ("pg_dump", dbname, "-t", table, "-Fd", "-f", directory),
        stderr=subprocess.PIPE,
        text=True,
    )
    _, err = process.communicate()
    return_code = process.wait()
    if return_code != 0:
        raise Exception(err)


def get_files(cnx, table, eid_column):
    """Return related files.

    :param Connection cnx: CubicWeb database connection
    :param str table: table name

    :returns: list of diskname-arcname tuples for found files
    :rtype: list
    """
    rows = cnx.system_sql("SELECT {}, file FROM {}".format(eid_column, table)).fetchall()
    arcnames = []
    for row in rows:
        if not os.path.exists(row[1]):
            print("file {} has not been found".format(row[1]))
            arcnames.append((None, row[0]))
        else:
            arcnames.append((os.path.join("files", os.path.basename(row[1])), row[0]))
    # update database to export the arcnames instead of the names of the files on the hard disk
    # or None if file has not been found
    cnx.cnxset.cu.executemany(
        "UPDATE {} SET file=%s WHERE {}=%s".format(table, eid_column), arcnames
    )
    # return list of found files
    return [(row[1], arcname[0]) for row, arcname in zip(rows, arcnames) if arcname[0]]


def dump_data(cnx, output_dir, formats):
    """Dump commemoration data.

    :param Connection cnx: CubicWeb database connection
    :param str output_dir: output directory basename
    :param tuple formats: list of export formats
    """
    FTABLES = {
        "public.commemo_images_dump": "commemo_eid",
        "public.commemo_programm_files_dump": "programm_file_eid",
        "public.commemo_dump_csv": "commemo_eid",
        "public.commemo_collection_images_dump": "collection_eid",
    }
    for table in TABLE_NAMES:
        print("-> write {}".format(table))
        if table in FTABLES.keys():
            for file_tuple in get_files(cnx, table, FTABLES[table]):
                yield file_tuple
        for fmt in formats:
            path = os.path.join(output_dir, table.split(".")[1])
            if fmt == "csv":
                if table == "public.commemo_dump":  # dump as pg only
                    continue
                path += ".csv"
                with open(path, "w") as fp:
                    cnx.cnxset.cu.copy_expert(
                        """COPY {} TO STDOUT
                        WITH (FORMAT CSV, DELIMITER '\t', NULL '', HEADER)""".format(
                            table
                        ),
                        fp,
                    )
            else:
                if table == "public.commemo_dump_csv":  # dump as CSV only
                    continue
                # use pg_dump
                path += "_pg"
                run_pg_dump(cnx, table, path)
            yield (path, os.path.basename(path))


def init_temp_tables(cnx, output_dir):
    """Initialize temporary tables.

    :param Connection cnx: CubicWeb database connection
    :param str output_dir: output directory basename
    """
    # delete any trailing temporary tables
    delete_tables(cnx)
    # create and fill temporary tables
    create_tables(cnx)
    # update values
    update_uris(cnx)
    update_files(cnx, output_dir)
    # commit changes
    cnx.commit()


def create_dumps(cnx, output_dir, formats):
    """Create dump(s) of commemoration data.

    :param Connection cnx: CubicWeb database connection
    :param str output_dir: output directory basename
    :param list formats: list of export formats
    """
    archive = "{}.zip".format(output_dir)
    try:
        init_temp_tables(cnx, output_dir)
        filenames = list(dump_data(cnx, output_dir, formats))
    except Exception as exception:
        print("error encountered while exporting ({})".format(exception))
        return
    finally:
        delete_tables(cnx)
        cnx.commit()
    print("\n-> wrote archive '{}'".format(archive))
    try:
        make_archive(archive, filenames)
    except Exception as exception:
        print("error encountered while exporting ({})".format(exception))
