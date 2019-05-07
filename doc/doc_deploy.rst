=======
 nginx
=======

Redirection des urls de l'ancien site
=====================================

Nous devons rediriger les urls de l'ancien site vers les nouvelles resources de
francearchives.fr.  Pour cela on utilise le module map de nginx. On commence par
générer un fichier de correspondance entre anciennes et nouvelles urls::

  cubicweb-ctl fa-gen-redirect francearchives -o /chemin/vers/fichier/correspondance.conf

Ensuite il faut dire à nginx de renvoyer des 301 sur la base de ce fichier::

  http {
    map $uri $new {
      include /chemin/vers/fichier/correspondance.conf;
    }
    server {
      location /redirect {
        if ($new) {
          return 301 $new;
        }
        return 308 /;
      }
    }
  }


  
    

