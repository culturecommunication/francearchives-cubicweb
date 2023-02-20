/* global $ BASE_URL */
const choiceKey = 'FASiteSearchCategory'

function setupTypeAhead() {
    typeof $.typeahead === 'function' &&
        $.typeahead({
            input: '#norql',
            minLength: 1,
            maxItem: 30,
            hint: true,
            cache: false,
            matcher: true,
            group: 'etype',
            filter: false, // data is already filtered by elasticsearch
            accent: {
                from: 'ãàáäâẽèéëêìíïîõòóöôùúüûñç',
                to: 'aaaaaeeeeeiiiiooooouuuunc',
            },
            display: ['text', 'etype'],
            resultContainer: "div.typeahead__result",
            template:
                "<span class='link'>{{text}}</span> - <small>{{countlabel}}</small>",
            dynamic: true,
            source: {
                ajax: {
                    type: 'GET',
                    url: BASE_URL + '_suggest',
                    data: {
                        q: '{{query}}',
                        escategory:  window.localStorage[choiceKey],
                    },
                },
            },
            callback: {
                // Redirect to url after clicking or pressing enter
                onClickAfter: function (node, a, item) {
                    window.location.href = item.url // Set window location to site url
                },
            },
        })
}

function toggleSubtitiles(){
    const links = Array.prototype.slice
          .call(document.querySelectorAll('.media-subtitles-button a'))
          .forEach(function (link) {
              link.addEventListener('click', function () {
                  let label
                  let expanded = this.classList.contains('expanded'),
                         textid = link.getAttribute('aria-controls');
                  if (textid !== undefined) {
                      text = document.querySelector('#' + textid)
                       if (text !== undefined) {
                           if (expanded) {
                               this.setAttribute('aria-expanded', 'false')
                               this.classList.remove('expanded')
                               label = this.dataset.labelExpand
                           }  else {
                               this.setAttribute('aria-expanded', 'true')
                               this.classList.add('expanded')
                               label = this.dataset.labelCollapse
                           }
                           this.innerHTML = label
                               text.classList.toggle('hidden')
                       }}
              })
          })

}

function toggleCategoryChoice(category) {
    const currentChoice = window.localStorage[choiceKey]
    if (currentChoice.includes(category)) {
        window.localStorage[choiceKey] = currentChoice.replace(category, '')
    } else {
        window.localStorage[choiceKey] += category
    }
    setupTypeAhead()
}

function setupSearchBarForm() {
    const searchBarForm = document.querySelector('#search-bar-form')
    if (searchBarForm === null) {
        return ;
    }

    // Initialize localStorage values
    if (!(choiceKey in window.localStorage)) {
        window.localStorage[choiceKey] = 'archivessiteres'
    }

    // Check values from localStorage state
    if (window.localStorage[choiceKey].includes('archives')) {
        searchBarForm.rb1.checked = true
    }
    if (window.localStorage[choiceKey].includes('siteres')) {
        searchBarForm.rb2.checked = true
    }
    // Change localStorage onClik
    searchBarForm.rb1.onclick = function () {
        toggleCategoryChoice('archives')
    }

    searchBarForm.rb2.onclick = function () {
        toggleCategoryChoice('siteres')
    }

    searchBarForm.rb1.addEventListener('focus',  function () {
        $('#rbm1').addClass("focused")});

    searchBarForm.rb1.addEventListener('blur', function () {
        $('#rbm1').removeClass("focused")});

    searchBarForm.rb2.addEventListener('focus',  function () {
        $('#rbm2').addClass("focused")});

    searchBarForm.rb2.addEventListener('blur', function () {
        $('#rbm2').removeClass("focused")});

}

function setupEventGallery() {
    var events = document.getElementById('eventGallery')
    if (events) {
        $(events).lightSlider({
            item: 3,
            loop: false,
            slideMove: 1,
            easing: 'cubic-bezier(0.25, 0, 0.25, 1)',
            speed: 600,
            responsive: [
                {
                    breakpoint: 1500,
                    settings: {
                        item: 2,
                    },
                },
                {
                    breakpoint: 768,
                    settings: {
                        item: 1,
                    },
                },
            ],
        })
    }
}


function setupHighresImagesDownloading() {
    var width = $(window).width()

    var hrPropName

    if (width >= 1900) {
        hrPropName = 'highresXl'
    } else if (width >= 1200) {
        hrPropName = 'highresLg'
    } else if (width >= 922) {
        hrPropName = 'highresMd'
    } else if (width >= 768) {
        hrPropName = 'highresSm'
    } else {
        hrPropName = 'highresXs'
    }

    Array.prototype.slice
        .call(document.querySelectorAll('.hero-images--image'))
        .forEach(function (img) {
            var hrImage = new Image()
            hrImage.onload = function () {
                img.src = this.src
                img.classList.remove('hero-images--image__lowres')
            }
            hrImage.src = img.dataset[hrPropName]
        })
}

function setupLightSlider() {
    if (
        $.fn.lightSlider !== undefined &&
        document.getElementById('light-slider')
    ) {
        var idxActive = $('#light-slider li span').index(
            $('#light-slider li span.active'),
        )

        /* slider XXX do that only on Commemo pages */
        var slider = $('#light-slider').lightSlider({
            pager: false,
            autoWidth: true,
        })
        slider.goToSlide(idxActive)

        $('.control-left').click(function () {
            slider.goToPrevSlide()
        })

        $('.control-right').click(function () {
            slider.goToNextSlide()
        })
    }
}

function setupFacets() {
    $('.facet-etype').click(function () {
        var url = $(this).data('url')
        if (url !== undefined) {
            document.location.href = url
        }
    })

    // panels
    function togglePanel(panelHeader) {
        var body = panelHeader.parent().next()
        var panelIsFolded = body.css('display') === 'none'
        if (panelIsFolded) {
            body.show()
            panelHeader.removeClass('folded').addClass('unfolded')
            panelHeader.attr('aria-expanded', 'true')
            panelHeader.parent()
                .siblings('.facet__body')
                .find('.facet__focusable-item:first')
                .focus()
        } else {
            body.hide()
            panelHeader.removeClass('unfolded').addClass('folded')
            panelHeader.attr('aria-expanded', 'false')
        }
    }

    // facets
    $('.cwjs-facet-title').click(function (e) {
        togglePanel($(this))
        e.preventDefault()
    })
    $('.cwjs-facet-title').keydown(function (e) {
        // 38 ArrowUp, 40 ArrowDown
        if (!/(38|40)/.test(e.keyCode)) return
        const title = this.parentNode
        e.preventDefault()
        e.stopPropagation()
        var panelIsFolded = $(title).next().css('display') === 'none'
        if (panelIsFolded) {
            togglePanel($(this))
        }
    })

    // commemoration content
    $('.commemoration-side-content-header').click(function () {
        togglePanel($(this))
    })
}

function resizeHeroImages() {
    if ($(window).width() < 992) {
        return
    }

    var totalHeight = $(window).height()
    var navbarHeight = $('.navtools').outerHeight()
    var heroHeight = $('#hero-images').outerHeight()
    var searchbarHeight = $('#home-search-bar').outerHeight()
    var sectionsHeight = $('#content-headings').outerHeight()

    heroHeight = totalHeight - navbarHeight - searchbarHeight - sectionsHeight

    /* Why 215? Why not?! */
    if (heroHeight > 215) {
        $('#hero-images').css({height: heroHeight + 'px'})
        $('.hero-images--item').css({height: heroHeight + 'px'})
        $('.hero-images--image').css({height: heroHeight + 'px'})
    }
}

function resizeResultImages() {
    Array.prototype.slice
        .call(document.querySelectorAll('.image-fixed-frame'))
        .forEach(function (frame) {
            var fixedFrame = $(frame)
            var insideImage = $(frame).find('img')
            insideImage.on('load', function () {
                var newMargin =
                    (fixedFrame.outerHeight() - insideImage.outerHeight()) / 2
                $(frame)
                    .find('img')
                    .css({'margin-top': newMargin + 'px'})
            })
        })
}

function setupFacetOptions() {
    $('.facet__more_options').click(function () {
        var $link = $(this)
        $link.children('a').toggle('hidden')
        $link.siblings('.more-option').toggle('hidden')
        $link.toggleClass('open')
        if ($link.hasClass('open')) {
            $link
                .siblings('.facet__value.more-option:first')
                .find('.facet__focusable-item')
                .focus()
        }
        return false
    })
    $('.facet__more_options').keydown(function (e) {
        if (!/(38|40)/.test(e.keyCode)) return
        e.preventDefault()
        e.stopPropagation()
        $(this).click()
    })
}


function setupSitemap() {
    var container = $('#tree-container')
    if (container.length !== 1) {
        // not on sitemap page
        return
    }
    $('i.fold', container).click(function () {
        var $caret = $(this)
        if ($caret.hasClass('rotate-0')) {
            $caret.removeClass('rotate-0')
            $caret.addClass('rotate-90')
        } else {
            $caret.addClass('rotate-0')
            $caret.removeClass('rotate-90')
        }
        var children = $caret.siblings('ul')
        children.toggleClass('hidden')
    })
}

function h(tagName, attrs) {
    var element = document.createElement(tagName),
        attrName = null,
        attrValue = null,
        args = Array.prototype.slice.call(arguments, 2)
    if (attrs !== null) {
        for (attrName in attrs) {
            attrValue = attrs[attrName]
            if (attrName === 'className') {
                attrName = 'class'
            }
            element.setAttribute(attrName, attrValue)
        }
    }
    args.forEach(function (child) {
        if (typeof child === 'string') {
            element.appendChild(document.createTextNode(child))
        } else {
            element.appendChild(child)
        }
    })
    return element
}

var overlay = h(
    'div',
    {className: 'overlay'},
    h('i', {className: 'overlay__loading fa fa-spin fa-spinner'}),
)


function setupEscapeButton() {
    $(document).keyup(function (e) {
        // close elements
        var selectors = [
            ['#menu-icon.open', '.menu-item :focus'],
            ['#languageMenu.open', '.languageMenu__menu-item :focus'],
            ['.cwjs-facet-title.unfolded', '.facet__focusable-item:focus'],
        ]
        var $elt, itemSelector, focused
        if (e.key === 'Tab') {
            selectors.forEach(function (selector) {
                var $elt = $(selector[0]),
                    itemSelector = selector[1]
                if (selector[0] === '.cwjs-facet-title.unfolded') {
                    focused = $elt.parent().siblings('.facet__body').find(itemSelector)
                } else {
                    focused = $(itemSelector)
                }
                if ($elt[0] !== undefined) {
                    if (focused.length === 0) {
                        $elt.click()
                    }
                }
            })
        }
        if (e.key === 'Escape') {
            selectors.some(function (selector) {
                var $elt = $(selector[0])
                if ($elt[0] !== undefined) {
                    $elt.click()
                    return true
                }
            })
        }
    })
}

// When the user scrolls down 50px from the top of the document, show the button
window.addEventListener('scroll', scrollFunction)

function scrollFunction() {
    const btn = document.getElementById('toTopBtn')
    if (btn === null) {
        return
    }
    if (
        document.body.scrollTop > 50 ||
        document.documentElement.scrollTop > 50
    ) {
        btn.style.display = 'block'
        btn.style.transition = 'opacity 1s ease-out'
    } else {
        btn.style.display = 'none'
        btn.style.transition = 'opacity 1s ease-out'
    }
}

function initScrollBtn() {
    // When the user clicks on the button, scroll to the top of the document
    $('#toTopBtn').click(function () {
        $('body,html').animate({scrollTop: $('body').offset().top},500);

    })
}

function initXitiSLinks() {
    const xitiSLinksSelector = 'a[data-xiti-name]'
    $(document).on('click', xitiSLinksSelector, function () {
        const ds = this.dataset
        return xt_click(this, ds.xitiLevel, ds.xitiN2, ds.xitiName, ds.xitiType)
    })
    $(document).on('keypress', xitiSLinksSelector, function (event) {
        if (!/(13)/.test(e.keyCode)) return
        const ds = this.dataset
        return xt_click(this, ds.xitiLevel, ds.xitiN2, ds.xitiName, ds.xitiType)
    })
}

$('document').ready(function () {
    setupEscapeButton()
    resizeHeroImages()
    setupTypeAhead()
    setupSearchBarForm()
    setupHighresImagesDownloading()
    setupLightSlider()
    setupFacets()
    setupEventGallery()
    resizeResultImages()
    setupFacetOptions()
    setupSitemap()
    initScrollBtn()
    initXitiSLinks()
    toggleSubtitiles()

})

window.onresize = function () {
    resizeHeroImages()
}

$(function () {
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
    popoverTriggerList.map(function (popoverTriggerEl) {
        let tot = new bootstrap.Popover(popoverTriggerEl)
        // accessibility: do not display title which is empty
        tot._element.removeAttribute("title")
    })
})
