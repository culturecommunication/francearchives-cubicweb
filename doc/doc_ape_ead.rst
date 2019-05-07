Services Web spécifiques
========================

OAI-PMH
-------

On implémente les 6 types de requêtes (verbes) du protocole :

* Identify
* ListMetadataFormats
* GetRecord
* ListIdentifiers
* ListRecords
* ListSets

Formats supportés
~~~~~~~~~~~~~~~~~~~

Le seul format suporté actuellement est le format apeEAD
(``metadataPrefix=ape_ead``).


Moissonnage sélectif
~~~~~~~~~~~~~~~~~~~~

On supporte le moissonnage sélectif des instruments de recherche à l'aide des Sets_ :

 * `findingaid` : export de tous les instruments de recherche publiés ;
 * `findingaid:service:<code_service>` : export de tous les
   instruments publiés d'un service particulier.

Ainsi une requête pour obtenir la liste de tous les instruments de recherche publiés de la Vendée
prend la forme : ``https://francearchives.fr/oai?verb=ListRecords&metadataPrefix=ape_ead&set=findingaid:service:FRAD085``


Exemple de requêtes
~~~~~~~~~~~~~~~~~~~

* `Identify` :

   https://francearchives.fr/oai?verb=Identify


* `ListMetadataFormats` :

   https://francearchives.fr/oai?verb=ListMetadataFormats

* `ListSets` :

   https://francearchives.fr/oai?verb=ListSets

* `ListIdentifiers` avec ou sans filtrage `set` :

   https://francearchives.fr/oai?verb=ListIdentifiers&metadataPrefix=ape_ead
   https://francearchives.fr/oai?verb=ListIdentifiers&metadataPrefix=ape_ead&set=findingaid
   https://francearchives.fr/oai?verb=ListIdentifiers&metadataPrefix=ape_ead&set=findingaid:service:FRAD071


* `ListRecords` avec ou sans filtrage `set` et `metadataPrefix`:

   https://francearchives.fr/oai?verb=ListRecords&metadataPrefix=ape_ead
   https://francearchives.fr/oai?verb=ListRecords&metadataPrefix=ape_ead&set=findingaid:service:FRAD090

* `GetRecord` avec spécification de l'`identifier`
   La valeur `stable_id` correspond à la dernière partie de l'url
   d'un instrument de recherche.

   Ainsi pour https://francearchives.fr/findingaid/8b4af219170a56f4586f231d05df132b1d3dbfc4
   la valeur `stable_id` est `8b4af219170a56f4586f231d05df132b1d3dbfc4` ce qui donne la requête
   suivante :

   https://francearchives.fr/oai?verb=GetRecord&metadataPrefix=ape_ead&identifier=8b4af219170a56f4586f231d05df132b1d3dbfc4

Format des enregistrements `record` des réponses OAI-PMH
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pour les requêtes `GetRecord` et `ListRecords`, la réponse OAI-PMH contient
deux balises à l'intérieur de la (ou des) balise(s) ``<record>`` :

* la balise ``<header>``, qui contient l'`identifier` de l'enregistrement
  ainsi que sa date de modification ;

* la balise ``<metadata>`` qui contient les données de l'enregistrement dont
  le format dépend du type d'objet de la requête.

La balise ``<metadata>`` contient une représentation RDF des entités.


.. _Set:
.. _Sets: http://www.openarchives.org/OAI/openarchivesprotocol.html#Set
    <baseurl>oai?verb=ListRecords&set=magazine&metadataPrefix=oai_dc
