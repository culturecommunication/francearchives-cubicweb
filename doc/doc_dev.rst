
Problèmes potentiels
--------------------

Si vous tombez sur l'erreur suivante::

    yams._exceptions.BadSchemaDefinition: (File, String) already defined for uuid

La version courte pour la corriger, c'est probablement::

    rm $VIRTUAL_ENV/local/lib

Pour mémoire, cette erreur est a priori liée à la présence du lien symbolique
créé par virtualenv depuis ``$VIRTUAL_ENV/local/lib`` vers ``$VIRTUAL_ENV/lib``
qui génère une "incohérence" entre le chemin du fichier associé aux modules dans
``sys.modules`` et ce que trouve ``pkgutil.ImpLoader.get_filename()``::

    >>> import cubicweb_file
    >>> cubicweb_file.__file__
    '/home/adim/.virtualenvs/francearchives/local/lib/python2.7/site-packages/cubicweb_file/__init__.pyc'
    >>> import pkgutil
    >>> loader = pkgutil.get_loader('cubicweb_file')
    >>> loader.get_filename()
    '/home/adim/.virtualenvs/francearchives/lib/python2.7/site-packages/cubicweb_file/__init__.py'

La conséquence, c'est que le nettoyage des modules avec ``logilab.common.modutils.cleanup_sys_modules``
ne se fait pas correctement.

Lancer le scan SonarQube
------------------------

Installer sonar-scanner https://docs.sonarqube.org/display/SCAN/Analyzing+with+SonarQube+Scanner

En utilisant tox ::

  export SONAR_URL=
  tox -e sonar

En ligne de commande ::

  export SONAR_URL=
  sonar-scanner --define sonar.projectVersion=`python setup.py --version`--define sonar.host.url=$SONAR_URL"
