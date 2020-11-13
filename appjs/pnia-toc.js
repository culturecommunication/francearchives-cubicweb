/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2020
 * Contact http://www.logilab.fr -- mailto:contact@logilab.fr
 *
 * This software is governed by the CeCILL-C license under French law and
 * abiding by the rules of distribution of free software. You can use,
 * modify and/ or redistribute the software under the terms of the CeCILL-C
 * license as circulated by CEA, CNRS and INRIA at the following URL
 * "http://www.cecill.info".
 *
 * As a counterpart to the access to the source code and rights to copy,
 * modify and redistribute granted by the license, users are provided only
 * with a limited warranty and the software's author, the holder of the
 * economic rights, and the successive licensors have only limited liability.
 *
 * In this respect, the user's attention is drawn to the risks associated
 * with loading, using, modifying and/or developing or reproducing the
 * software by the user in light of its specific status of free software,
 * that may mean that it is complicated to manipulate, and that also
 * therefore means that it is reserved for developers and experienced
 * professionals having in-depth computer knowledge. Users are therefore
 * encouraged to load and test the software's suitability as regards their
 * requirements in conditions enabling the security of their systemsand/or
 * data to be ensured and, more generally, to use and operate it in the
 * same conditions as regards security.
 *
 * The fact that you are presently reading this means that you have had
 * knowledge of the CeCILL-C license and that you accept its terms.
 */

/* global StickySidebar */

import {each} from 'lodash/collection'

function initToc() {
    var sidebar = new StickySidebar('.sticky-toc', {
        topSpacing: 20,
        bottomSpacing: 20,
        containerSelector: '.article__content',
        innerWrapperSelector: '.ui-toc',
    })
    return sidebar
}

function buildToc(uitoc) {
    if (uitoc === null) {
        return
    }
    initToc()

    const nested = uitoc.querySelectorAll('.toc ul')
    // hide h+1 summary level(
    each(nested, (ul) => {
        ul.classList.add('hidden')
    })
    const toc = uitoc.querySelector('.toc'),
        toggleLink = uitoc.querySelector('.toc-links .toggle-menu')

    if (uitoc.querySelectorAll('.toc ul.hidden').length === 0) {
        toggleLink.classList.add('hidden')
    }

    function toggleToc() {
        let label
        if (toc.classList.contains('expanded')) {
            each(nested, (ul) => {
                ul.classList.add('hidden')
            })
            label = toggleLink.dataset.labelCollapse
        } else {
            each(nested, (ul) => {
                ul.classList.remove('hidden')
            })
            toggleLink.dataset['collapsed'] = false
            label = toggleLink.dataset.labelExpand
        }
        toc.classList.toggle('expanded')
        toggleLink.innerHTML = label
    }

    function initMenuLinks() {
        toggleLink.addEventListener('click', function (e) {
            e.preventDefault()
            e.stopPropagation()
            toggleToc()
        })
    }

    initMenuLinks()

    each(toc.querySelectorAll('.toc > li > a[href^="#"]'), (anchor) => {
        anchor.addEventListener('click', function (e) {
            each(nested, (ul) => {
                ul.classList.add('hidden')
            })
            each(e.target.parentNode.querySelectorAll('ul'), (ul) => {
                ul.classList.remove('hidden')
            })
            e.stopPropagation() // do not close the menu
        })
    })

    const navTargetPairs = getTargetPairs()

    function getTargetPairs() {
        let pairs = [],
            link
        each(toc.querySelectorAll('li'), (li) => {
            link = li.firstElementChild.getAttribute('href')
            if (link !== null) {
                pairs.push([li, document.getElementById(link.slice(1))])
            }
        })
        each(pairs, (pair, idx) => {
            if (idx + 1 < pairs.length) {
                pair.push(pairs[idx + 1][1])
            }
        })
        return pairs
    }

    function isPartlyInViewPort(elt, nextElt) {
        const top = elt.getBoundingClientRect().top
        let bottom
        if (nextElt === undefined) {
            // take the parent as nextElement of the last target
            // to get the right bottom boundary in isPartlyInViewPort
            bottom = elt.parentNode.getBoundingClientRect().bottom
        } else {
            const styles = window.getComputedStyle(nextElt),
                marginTop = parseInt(styles.marginTop) || 0
            bottom = nextElt.getBoundingClientRect().top - marginTop
        }
        return (
            (top >= 0 && top <= window.innerHeight) ||
            (bottom >= 0 && bottom <= window.innerHeight) ||
            (bottom > 0 && top < 0)
        )
    }

    window.addEventListener('scroll', () => {
        for (let [li, target, nextElt] of navTargetPairs) {
            if (isPartlyInViewPort(target, nextElt)) {
                li.classList.add('active')
            } else {
                li.classList.remove('active')
            }
        }
    })
}

document.addEventListener('DOMContentLoaded', () =>
    buildToc(document.querySelector('.ui-toc')),
)
