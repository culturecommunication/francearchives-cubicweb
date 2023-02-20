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
/* global $ */

class FaqNavigation {
    constructor(node) {
        if (!node) return
        this.faqNode = node

        this.questions = this.faqNode.querySelectorAll('.faq_item__question')
        for (let i = 0; i < this.questions.length; i++) {
            let ti = this.questions[i]
            ti.addEventListener('keydown', this.onKeydown.bind(this))
        }
        let label
        document
            .getElementById('faq-toggle-fold')
            .addEventListener('click', function () {
                const collapables = $('.faq_item .collapse')
                if (this.classList.contains('expanded')) {
                    collapables.collapse('hide')
                    this.setAttribute('aria-expanded', 'false')
                    label = this.dataset.labelExpand
                } else {
                    collapables.collapse('show')
                    this.setAttribute('aria-expanded', 'true')
                    label = this.dataset.labelCollapse
                }
                this.innerHTML = label
                this.classList.toggle('expanded')
            })

        const trigger = document.getElementById('faqbox-btn')
        if (trigger) this.initModal(trigger)
    }

    initModal(trigger) {
        // used in modal box
        const dialog = document.getElementById(
            trigger.getAttribute('aria-controls'),
        )
        const page = document.getElementById('page')
        const open = function (dialog, trigger) {
            dialog.setAttribute('aria-hidden', false)
            page.setAttribute('aria-hidden', true)
            trigger.setAttribute('aria-expanded', 'true')
        }

        const close = function (dialog, trigger) {
            dialog.setAttribute('aria-hidden', true)
            page.setAttribute('aria-hidden', false)
            trigger.setAttribute('aria-expanded', 'false')
        }

        // open dialog
        dialog.addEventListener('show.bs.modal', function () {
            open(dialog, trigger)
        })

        trigger.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault()
                trigger.click()
            }
        })

        // close dialog
        dialog.addEventListener('hide.bs.modal', function () {
            close(dialog, trigger)
        })

        dialog.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                close(dialog, trigger)
            }
        })
    }

    // Event handlers

    isExpanded(item) {
        return item.getAttribute('aria-expanded') === 'true'
    }

    toggleAnswer(item) {
        if (item.getAttribute('aria-controls')) {
            item.click()
        }
    }

    setFocusToNextQuestion(tgt) {
        var next = false
        for (var i = this.questions.length - 1; i >= 0; i--) {
            var ti = this.questions[i]
            if (ti === tgt) {
                break
            }
            next = ti
        }
        if (next) {
            next.focus()
        }
    }

    setFocusToPreviousQuestion(tgt) {
        var prev = false
        for (var i = 0; i < this.questions.length; i++) {
            var ti = this.questions[i]
            if (ti === tgt) {
                break
            }
            prev = ti
        }
        if (prev) {
            prev.focus()
        }
    }
    onKeydown(event) {
        var tgt = event.currentTarget,
            flag = false,
            key = event.key

        if (event.altKey || event.ctrlKey || event.metaKey || event.shift) {
            return
        }
        switch (key) {
            // NOTE: Return key is supported through the click event
            case 'Enter':
                tgt.click()
                flag = true
                break
            case ' ':
                flag = true
                break
            case 'Up':
            case 'ArrowUp':
                if (this.isExpanded(tgt)) {
                    this.toggleAnswer(tgt)
                } else {
                    this.setFocusToPreviousQuestion(tgt)
                }

                flag = true
                break
            case 'Down':
            case 'ArrowDown':
                if (!this.isExpanded(tgt)) {
                    this.toggleAnswer(tgt)
                } else {
                    this.setFocusToNextQuestion(tgt)
                }
                flag = true
                break
            default:
                break
        }

        if (flag) {
            event.stopPropagation()
            event.preventDefault()
        }
    }
}

document.addEventListener(
    'DOMContentLoaded',
    () => new FaqNavigation(document.getElementById('faqs')),
)
