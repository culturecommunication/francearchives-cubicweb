Summary
=======

Cube applicatif pour FranceArchives https://francearchives.fr/

Ce cube utilise le framework CubicWeb https://www.cubicweb.org/

Les dépendances sont décrites dans le packaging python (`__pkginfo__.py`) et
javascript (`package.json`).

Copie d'écran
-------------

.. image:: francearchives_screenshot.jpg

Licence
-------

cubicweb-francearchives is released under the terms of the CeCiLL v2 license.

La licence complète peut être trouvée dans ce dépot `LICENCE.txt` et
https://cecill.info/licences/Licence_CeCILL_V2.1-fr.html


Black
-----

Pour lancer **black** ::

  black --config pyproject.toml .

Ajouter **black** dans les hooks **hg** ::

créer le script `path_hook` (exemple de code) ::

  #!/bin/sh
  for fpath in $(hg status --no-status --modified --added | grep ".py$") ; do
    black ${fpath}
  done

et appeler le ̀.hg\hgrc` du projet ::

  [hooks]
  precommit = path_to_hook
  pre-amend = path_to_hook


il est possible d'intégrer la config utilisée pour le projet ::

  #!/bin/sh
  for fpath in $(hg status --no-status --modified --added | grep ".py$") ; do
    black --config $1 ${fpath}
  done


et appeler le ̀.hg\hgrc` du projet ::

  [hooks]
  precommit = path_to_hook pyproject.toml
  pre-amend = path_to_hook pyproject.toml



Compilier les css
-----------------

Il est nécessaire d'installer l'outil ``ruby-sass``.

1. Pour compiler la feuille des styles unique utiliser la commande suivante :

   sass scss/main.scss:cubicweb_francearchives/data/css/francearchives.bundle.css

2. Utiliser -watch pour tenir compte des modifications :

   sass --watch scss/main.scss:cubicweb_francearchives/data/css/francearchives.bundle.css

Création d'un virtualenv
------------------------

La création d'une instance se fait traditionnellement via un virtualenv.
Pour créer le virtualenv lancez la commande ``mkvirtualenv $NAME`` (paquet `virtualenvwrapper`).


Création d'une instance
-----------------------

Après avoir créé le virtualenv et téléchargé le dépôt francearchives, les prochaines étapes
sont d'installer les paquets requis et le cube lui-même.::

    cd $PATH_TO_CUBE_FRANCEARCHIVES
    pip install -r dev-requirements.txt
    pip install -e .

Ensuite créez une instance en utilisant la commande::

    cubicweb-ctl create francearchives $INSTANCE_NAME

Finalement il faut créer une fiche de configuration pyramid pour l'instance dans
$PATH_TO_INSTANCE/pyramid.ini (par défaut $PATH_TO_INSTANCE est
``$HOME/etc/cubicweb.d/$INSTANCE_NAME``).

Example::

    [main]
    cubicweb.bwcompat = no
    cubicweb.defaults = no

    cubicweb.includes =
        cubicweb.pyramid.auth
        cubicweb.pyramid.session

    cubicweb.auth.authtkt.session.secret = stuff
    cubicweb.auth.authtkt.persistent.secret = stuff
    cubicweb.auth.authtkt.session.secure = no
    cubicweb.auth.authtkt.persistent.secure = no
    cubicweb.session.secret = the-secret


Tests
-----
Lancer les tests avec tox
~~~~~~~~~~~~~~~~~~~~~~~~~

Vous aurez besoin de :

 * elasticsearch version 7.x installable en suivant ce guide https://www.elastic.co/guide/en/elasticsearch/reference/current/getting-started-install.html
 * ``sudo apt-get install poppler-utils`` (pour ``pdftotext``)
 * ``sudo apt-get install ruby-sass`` (pour ``sass``)

Pour lancer les tests ::

  tox

Pour lancer les tests en parallèle sur plusieurs CPUs, installez `pytest-xdist`.

Les données utilisées pour les tests ne correspondent pas aux données
réelles.

Ces fichiers ne doivent pas être utilisés dans un autre but que celui
de tester la présente application. Le ministère de la Culture décline
toute responsabilité sur les problèmes et inconvénients, de quelque
nature qu'ils soient, qui pourraient survenir en raison d'une
utilisation de ces fichiers à d'autres fins que de tester la présente
application.

**ElasticSearch et Pifpaf**

``pifpaf`` est utilisé pour permettre à ``tox`` de se servir des services installés en
local. Pour que ``pifpaf`` arrive à lancer ``elasticsearch`` il faut ::

 1. Ajouter le compte utilisateur servant a lancer ``tox`` au groupe ``elasticsearch``::

    usermod -a -G elasticsearch USER

 2. Modifier les permissions de `/etc/elasticsearch` ::

    chmod +rx /etc/elasticsearch
    chmod -R +r /etc/elasticsearch
    chmod +r /etc/default/elasticsearch

 3. Modifier les permissions du dossier ``/var/log/elasticsearch``::

    chmod 774 /var/log/elasticsearch

 4. Modifier les permissions du fichier ``/var/log/elasticsearch/gc.log``::

    chown USER /var/log/elasticsearch/gc.log
    chmod 664 /var/log/elasticsearch/gc.log

Lancer les tests a11y
~~~~~~~~~~~~~~~~~~~~~

1. Installer pa11y

   npm install pa11y

2. Lancer les tests

   BASEURL=<host:port>/fr  node a11y/test.js


Documentation supplémentaire
----------------------------

Des éléments supplémentaires de documentation sont dans `doc/`, dont notamment ::

* `doc_dev.rst` explique des problèmes qui peuvent être rencontrés
  lors de l'installation ;

* `doc_exploitation.rst` contient la configuration recommandée de ``pyramid``.

Contributrices et contributeurs
-------------------------------

Voici une liste non exhaustive des personnes ayant contribué à
ce logiciel (ordre alphabetique) :

* Adrien Di Mascio
* Arthur Lutz
* Carine Dengler
* David Douard
* Juliette Belin
* Katia Saurfelt
* Samuel Trégouët
* Sylvain Thénault
* Tanguy Le Carrour
