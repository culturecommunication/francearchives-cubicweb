/* global $ BASE_URL */

function setupTypeAhead() {
    typeof $.typeahead === 'function' && $.typeahead({
        input: '#norql',
        minLength: 1,
        maxItem: 30,
        hint: true,
        cache: false,
        matcher: true,
        filter: false,  // data is already filtered by elasticsearch
        accent: {
            from: "ãàáäâẽèéëêìíïîõòóöôùúüûñç",
            to: "aaaaaeeeeeiiiiooooouuuunc"
        },
        display: ['text', 'etype'],
        template: "<span class='link'>{{text}}</span>, <small>{{etype}}</small> - <small>{{countlabel}}</small>",
        dynamic: true,
        source: {
            ajax: {
                type: "GET",
                url: BASE_URL + '_suggest',
                data: {
                    q: "{{query}}"

                }
            }
        },
        callback: {
            // Redirect to url after clicking or pressing enter
            onClickAfter: function(node, a, item) {
                window.location.href = item.url; // Set window location to site url
            }
        }
    });
}


function setupEventGallery() {
    var events = document.getElementById('eventGallery');
    if (events) {
        $(events).lightSlider({
            item: 3,
            loop: false,
            slideMove: 1,
            easing: 'cubic-bezier(0.25, 0, 0.25, 1)',
            speed: 600,
            responsive: [{
                breakpoint: 1500,
                settings: {
                    item: 2
                }
            }, {
                breakpoint: 768,
                settings: {
                    item: 1
                }
            }]});
    }
}


function setupCarousel() {
    var items = Array.prototype.slice.call(document.querySelectorAll('.hero-images--item'));

    if (!items.length) {
        return;  // no carousel found
    }

    var curidx = 0,
        nbelts = items.length,
        curitem = items[0];

    function carouselNext() {
        var nextidx = (++curidx % nbelts),
            nextitem = items[nextidx];

        curitem.classList.remove('hero-images--item__visible');
        nextitem.classList.add('hero-images--item__visible');
        curitem = nextitem;
    }

    // start carousel
    window.setInterval(carouselNext, 3000);
}


function setupHighresImagesDownloading() {
    var width = $(window).width();

    var hrPropName;

    if (width >= 1900) {
        hrPropName = 'highresXl';
    } else if (width >= 1200) {
        hrPropName = 'highresLg';
    } else if (width >= 922) {
        hrPropName = 'highresMd';
    } else if (width >= 768) {
        hrPropName = 'highresSm';
    } else {
        hrPropName = 'highresXs';
    }

    Array.prototype.slice.call(document.querySelectorAll('.hero-images--image'))
        .forEach(function(img) {
            var hrImage = new Image();
            hrImage.onload = function() {
                img.src = this.src;
                img.classList.remove('hero-images--image__lowres');
            }
            hrImage.src = img.dataset[hrPropName];
        });
}


function setupAriaOnSearchInputRadio() {
    document.querySelector('#site-search-options').addEventListener('change', function() {
        $(this).find('input').each(function() {
            var $input = $(this);
            if ($input.is(':checked')){
                $input.attr('aria-checked', 'true');
            } else {
                $input.attr('aria-checked', 'false');
            }
       });
    }
)}


function linkToggleDropDowMenu($link, $trigger, $items) {
    $link.keydown(function(e){
        if (!$items.length) return;
        // no menu to open
        if (e.key !== 'Enter') return;
        e.preventDefault();
        e.stopPropagation();
        $trigger.click();
        if ($trigger.hasClass('open')) {
            $items.eq(0).focus();
        }
    });
}


function setupDropdownSiteMenu() {
    var $menu = $('#main-menu'),
        $items = $('#menu-panel a'),
        $icon =  $('#menu-icon');
    linkToggleDropDowMenu($menu, $icon, $items);
    $icon.click(function() {
       $('#menu-panel').toggleClass('hidden');
       $(this).toggleClass('open');
       if ($(this).hasClass('open')) {
           $menu.attr('aria-expanded', 'true');
           $('.menu-icon__menu-item a:first').focus();
       } else {
           $menu.attr('aria-expanded', 'false');
       }
    });
}


function setupSearchOptions() {
    var $link = $('.search-options-toggle'),
        $items = $('.search-options input');
    linkToggleDropDowMenu($link, $link, $items);
    $link.click(function() {
        $(this).siblings('.search-options').toggleClass("hidden");
        $(this).toggleClass('open');
        if ($(this).hasClass('open')) {
            $('.search-options-toggle__menu-item input:first').focus();
        }
    });

}


function setupLightSlider() {
    if ($.fn.lightSlider !== undefined &&
        document.getElementById('light-slider')) {
        var idxActive = $('#light-slider li span').index(
            $('#light-slider li span.active'));

        /* slider XXX do that only on Commemo pages */
        var slider = $("#light-slider").lightSlider({
            pager: false,
            autoWidth: true
        });
        slider.goToSlide(idxActive);

        $(".control-left").click(function(){
            slider.goToPrevSlide();
        });

        $(".control-right").click(function(){
            slider.goToNextSlide();
        });
    }

}


function setupFacets() {
    $('.facet-etype').click(function() {
        var url = $(this).data('url');
        if (url !== undefined) {
            document.location.href = url;
        }
    });

   // panels
   function togglePanel(panelHeader) {
       var body = panelHeader.next();
       var panelIsFolded = body.css('display') === 'none';

       if (panelIsFolded) {
           body.show();
           panelHeader.removeClass('folded').addClass('unfolded');
           panelHeader.siblings('.facet__body').find('.facet__focusable-item:first').focus();
       } else {
           body.hide();
           panelHeader.removeClass('unfolded').addClass('folded');
       }
   }

   // facets
   $('.cwjs-facet-title').click(function() {
       togglePanel($(this));
   });
   $('.cwjs-facet-title').keydown(function(e){
        if (!/(38|40)/.test(e.keyCode)) return;
        e.preventDefault();
        e.stopPropagation();
      var panelIsFolded = $(this).next().css('display') === 'none';
      if (panelIsFolded) {
           togglePanel($(this));
        }
   });

   // commemoration content
   $('.commemoration-side-content-header').click(function() {
       togglePanel($(this));
   });
}

function resizeHeroImages() {
    if ($(window).width() < 992) { return; }

    var totalHeight = $(window).height();
    var navbarHeight = $('.navtools').outerHeight();
    var heroHeight = $('#hero-images').outerHeight();
    var searchbarHeight = $('#home-search-bar').outerHeight();
    var sectionsHeight = $('#content-headings').outerHeight();

    heroHeight = totalHeight - navbarHeight -
                 searchbarHeight - sectionsHeight;

    /* Why 215? Why not?! */
    if (heroHeight > 215) {
        $('#hero-images').css({height: heroHeight + 'px'});
        $('.hero-images--item').css({height: heroHeight + 'px'});
        $('.hero-images--image').css({height: heroHeight + 'px'});
    }
}

function resizeResultImages() {
    Array.prototype.slice.call(document.querySelectorAll('.image-fixed-frame'))
        .forEach(function(frame) {
            var fixedFrame = $(frame);
            var insideImage = $(frame).find('img');
            insideImage.on('load', function() {
                var newMargin
                    = (fixedFrame.outerHeight() - insideImage.outerHeight()) / 2;
                $(frame).find('img').css({'margin-top': newMargin + 'px'});
            })
        });
}


function setupFacetOptions() {
     $('.facet__more_options').click(function() {
         var $link = $(this);
         $link.children('a').toggle('hidden');
         $link.siblings('.more-option').toggle('hidden');
         $link.toggleClass('open');
         if ($link.hasClass('open')) {
             $link.siblings('.facet__value.more-option:first').find('.facet__focusable-item').focus();
         }
         return false;
     });
     $('.facet__more_options').keydown(function(e) {
        if (!/(38|40)/.test(e.keyCode)) return;
        e.preventDefault();
        e.stopPropagation();
           $(this).click();
        });
}

function setupSitemap() {
    var container = $('#tree-container');
    if (container.length !== 1) {
        // not on sitemap page
        return;
    }
    $('i.fold', container).click(function() {
        var $caret = $(this);
        if ($caret.hasClass('rotate-0')) {
            $caret.removeClass('rotate-0');
            $caret.addClass('rotate-90');
        } else {
            $caret.addClass('rotate-0');
            $caret.removeClass('rotate-90');
        }
        var children = $caret.siblings('ul');
        children.toggleClass('hide');
    });
}


function h(tagName, attrs) {
    var element = document.createElement(tagName),
        attrName = null,
        attrValue = null,
        args = Array.prototype.slice.call(arguments, 2);
    if (attrs !== null) {
        for (attrName in attrs) {
            attrValue = attrs[attrName];
            if (attrName === 'className') {
                attrName = 'class';
            }
            element.setAttribute(attrName, attrValue);
        }
    }
    args.forEach(function(child) {
        if (typeof child === 'string') {
            element.appendChild(document.createTextNode(child));
        } else {
            element.appendChild(child);
        }
    });
    return element;
}

var overlay = h('div', {className: 'overlay'},
                h('i', {className: 'overlay__loading fa fa-spin fa-spinner'}));

function setupAncestorsFacet() {
    var container = document.getElementById('facet-ancestors');
    if (container === null) {
        // no ancestors facet on this page
        return;
    }

    // container.style.position = 'relative';
    container.appendChild(overlay);

    var lis = container.querySelectorAll('li.facet__value'),
        eid2li = {},
        eid = null,
        tree = [],
        sections = [];

    for (var i = 0, l = lis.length ; i < l ; i++) {
        eid = lis[i].dataset.eid;
        eid2li[eid] = lis[i];
        sections.push(Number(eid));
    }
    fetch(BASE_URL + '_children', {credentials: 'same-origin'})
        .then(function(res) { return res.json(); })
        .then(function(db) {
            // first we build tree data structure
            function fill_branch(el, branch) {
                if (db.hasOwnProperty(el)) {
                    db[el].forEach(function(child) {
                        if (sections.indexOf(child) === -1) {
                            return;
                        }
                        branch[1].push(fill_branch(child, [child, []]));
                    });
                }
                // remove child from sections
                var index = sections.indexOf(el);
                sections.splice(index, 1);
                return branch;
            }
            while (sections.length) {
                tree.push(fill_branch(sections[0], [sections[0], []]));
            }

            // then we create ul/li structure
            var topul = container.querySelector('.facet__values');
            function buildUlLi(ul, data) {
                data.forEach(function(d) {
                    var sectionEid = d[0],
                        children = d[1],
                        li = eid2li[sectionEid];
                    li.style.display = '';
                    li.classList.remove('more-option');
                    var liClass = 'fa fold pointer fa-caret-right rotate-0' +
                        (children.length ? '' : ' not-visible');
                    li.appendChild(
                        h(
                            'div',
                            null,
                            h('i', {className: liClass}),
                            li.children[0]
                        )
                    );
                    if (children.length) {
                        var nextUl = h('ul', {className: 'hide children'});
                        li.appendChild(buildUlLi(nextUl, children));
                    }
                    ul.appendChild(li);
                });
                return ul;
            }
            buildUlLi(topul, tree);

            // hide more option if any
            var moreOpts = container.querySelector('.facet__more_options');
            if (moreOpts) {
                moreOpts.classList.add('hide');
            }

            // add action on caret
            topul.addEventListener('click', function(ev) {
                var i = ev.target,
                    classList = i.classList;
                if (!classList.contains('fold')) {
                    return;
                }
                classList.toggle('rotate-0');
                classList.toggle('rotate-90');
                var ul = i.parentElement.parentElement.querySelector('ul');
                if (!ul) {
                    return;
                }
                ul.classList.toggle('hide');
            });
            container.removeChild(overlay);
        })
        .catch(function(err) {
            console.error(err);
        });
}

function setupEscapeButton(){
    $(document).keyup(function(e) {
        // close elements
        var selectors = [['#menu-icon.open', '.menu-icon__menu-item :focus'],
            ['#languageMenu.open', '.languageMenu__menu-item :focus'],
            ['.search-options-toggle.open', '.search-options__menu-item :focus'],
            ['.cwjs-facet-title.unfolded', '.facet__focusable-item:focus'],
        ];
        var $elt, itemSelector, focused;
        if (e.key === 'Tab') {
            selectors.forEach(function(selector) {
                var $elt = $(selector[0]),
                    itemSelector = selector[1];
                if (selectors[0] === '.cwjs-facet-title.unfolded') {
                    focused = $elt.siblings('.facet__body').find(itemSelector);
                } else {
                    focused = $(itemSelector);
                }
                if ($elt[0] !== undefined) {
                    if ( focused.length === 0){
                        $elt.click();
                    }
                }
            });
        }
        if (e.key === 'Escape') {
            selectors.some(function(selector) {
                var $elt = $(selector[0]);
                if ($elt[0] !== undefined ) {
                    $elt.click();
                    return true;
                }
            });
        }
    });
}


// When the user scrolls down 20px from the top of the document, show the button
window.addEventListener('scroll', scrollFunction);

function scrollFunction() {
  const btn = document.getElementById("toTopBtn");
  if (btn === null) {
      return;
  }
  if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
      btn.style.display = "block";
  } else {
      btn.style.display = "none";
  }
}

function initScrollBtn() {
// When the user clicks on the button, scroll to the top of the document
  $("#toTopBtn").click(function(){
      document.body.scrollTop = 0; // For Safari
      document.documentElement.scrollTop = 0; // For Chrome, Firefox, IE and Opera
  });
}

$('document').ready(function(){
    setupEscapeButton();
    resizeHeroImages();
    setupTypeAhead();
    setupCarousel();
    setupHighresImagesDownloading();
    setupLightSlider();
    setupDropdownSiteMenu();
    setupSearchOptions();
    setupFacets();
    setupEventGallery();
    resizeResultImages();
    setupFacetOptions();
    setupSitemap();
    setupAncestorsFacet();
    setupAriaOnSearchInputRadio();
    initScrollBtn()
});

window.onresize = function() {
    resizeHeroImages();
}

