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

Tests
-----

Pour lancer les tests ::

  tox

Les données utilisées pour les tests ne correspondent pas aux données
réelles.

Ces fichiers ne doivent pas être utilisés dans un autre but que celui
de tester la présente application. Le ministère de la Culture décline
toute responsabilité sur les problèmes et inconvénients, de quelque
nature qu'ils soient, qui pourraient survenir en raison d'une
utilisation de ces fichiers à d'autres fins que de tester la présente
application.


Pour lancer **black** ::

  black --config pyproject.toml .


Compilier les css
----------------

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

Lancer les tests a11y
----------------------

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
