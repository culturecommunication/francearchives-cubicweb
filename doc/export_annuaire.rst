Export CSV de l'annuaire des services
=====================================

Cette note décrit les champs du fichier CSV de l'annuaire des services généré via le script
*scripts/export_directory.py*. Les exemples sont tirés du premier paragraphe de la page
http://www.archivesdefrance.culture.gouv.fr/annuaire-services/entreprises/.

- **page** : la page correspondante sur www.archivesdefrance.culture.gouv.fr, laissée pour faciliter
  la correction du fichier CSV généré
- **category** : la catégorie correspond au titre h3 de la page, par exemple 'Archives d'entreprise'.
- **name** : nom de la sous-entité du service, récupéré si il y a un champ en gras dans le bloc,
  par exemple 'Académie François Bourdon'.
- **name2** : le premier champ non gras du bloc, par exemple 'Service des Archives'.
- **address** : cela devrait être seulement la première partie de l'adresse (hors code postal et ville),
  mais cela ne s'avérant pas possible à extraire de par l'absence de structure du bloc html, le choix
  a été fait de rentrer l'intégralité de l'adresse dans ce champ.
- **zip_code** : le code postal correspondant à l'adresse du service
- **city** : non rempli, à récupérer du champ **address**
- **website_url** : l'adresse du site web du service, si elle existe
- **contact_name** : le nom du contact dans le service. Correspond au deuxième champ suivant le champ
  en gras. Parfois, lorsqu'il n'y a pas de nom de contact, on y trouve la première partie de l'adresse.
  Parfois quand il y a un autre nom de sous-entité du service, il se retrouvera dans ce champ.
  Exemple de configuration correcte : 'Ivan Kharaba'.
- **phone_number** : récupéré toutes les fois où l'on trouve la chaîne "Tél. :" ou "tél. :" dans un
  bloc décrivant un service.
- **fax** : récupéré toutes les fois où l'on trouve la chaîne "télécopie :" ou "Télécopie :"
  dans un bloc décrivant un service.
- **email** : adresse email du service
- **annual_closure** : fermeture annuelle du service, récupéré toutes les fois où on trouve la chaîne
  "[f/F]ermeture annuelle :" ou "[f/F]ermeture :" dans un bloc décrivant un service.
- **opening_period** : non récupéré
- **réseaux sociaux**: récupérés depuis la page
  http://www.archivesdefrance.culture.gouv.fr/ressources/medias-sociaux/. Une fois les données
  décrites ci-dessus récupérées, les champs **category**, **name**, **name2** et **contact_name**
  de chaque service sont comparés aux noms associés aux réseaux sociaux. Si deux noms sont proches,
  alors le réseau social correspondant est ajouté aux données du service. Par exemple,
  'Archives départementales des Alpes-Maritimes' est similaire à 'Département des Alpes-Maritimes'.
  La page *Flickr* https://www.flickr.com/photos/ad06/ est donc ajoutée à tous les services du
  département des Alpes Maritimes.
  Catégories ajoutées de réseaux sociaux présentes dans le CSV : *Flux rss*, *Dailymotion*,
  *Scoop it*, *YouTube*, *Pinterest*, Vimeo*, *Twitter*, *Storify*, *Foursquare*, *Facebook*,
  *Wikimédia*, *Flickr*, *Blogs*.

