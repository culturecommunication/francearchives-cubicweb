/*
 *   This content is licensed according to the W3C Software License at
 *   https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document
 *
 *   File: treeview-navigation.js
 *   Desc: Tree item object for representing the state and user interactions for a
 *       tree widget for navigational links

 *   This software or document includes material copied from or
 *   derived from [Javascript: treeview-navigation.js and
 *   https://w3c.github.io/aria-practices/examples/treeview/js/treeview-navigation.js of the W3C document]. Copyright ©
 *   [YEAR] W3C® (MIT, ERCIM, Keio, Beihang).
 *
 */

/* global  $ */
'use strict'

class TreeViewNavigation {
    constructor(node) {
        // Check whether node is a DOM element
        if (typeof node !== 'object') {
            return
        }
        this.treeNode = node
        const fold = document.getElementById('fold-all-tree')
        var arrows = this.treeNode.querySelectorAll(
            '#section-tree .section-tree__section i.fold',
        )
        arrows.forEach((arrow) => {
            arrow.addEventListener('click', function () {
                var caret = this
                let label
                // if subsection was closed, open it
                if (caret.classList.contains('rotate-0')) {
                    caret.classList.remove('rotate-0')
                    caret.classList.add('rotate-90')
                    caret.setAttribute('aria-expanded', 'true')
                } else {
                    caret.classList.add('rotate-0')
                    caret.classList.remove('rotate-90')
                    caret.setAttribute('aria-expanded', 'false')
                }
                fold.innerHTML = label
                $(this).parent().parent().siblings('ul').toggleClass('d-none')
                const opened = node.querySelectorAll(
                    '#section-tree .section-tree__section i.fold[aria-expanded="true"]',
                )
                if (opened.length > 0) {
                    fold.setAttribute('aria-expanded', 'true')
                    fold.innerHTML = fold.dataset.labelCollapse
                } else {
                    fold.setAttribute('aria-expanded', 'false')
                    fold.innerHTML = fold.dataset.labelExpand
                }
            })
        })

        this.navNode = node.parentElement
        this.triggerTag = 'i'
        this.treeitems = this.treeNode.querySelectorAll('[role="treeitem"]')
        for (let i = 0; i < this.treeitems.length; i++) {
            let ti = this.treeitems[i]
            ti.addEventListener('keydown', this.onKeydown.bind(this))
            // first tree item is in tab sequence of page
            if (i === 0) {
                ti.tabIndex = 0
            } else {
                ti.tabIndex = -1
            }
        }
    }

    getParentTreeitem(treeitem) {
        var node = treeitem.closest('ul')
        if (node) {
            node = node.previousElementSibling
            if (node && node.getAttribute('role') === 'treeitem') {
                // remove me
                return node
            }
            node = node.getElementsByTagName(this.triggerTag)
            if (node && node[0].getAttribute('role') === 'treeitem') {
                return node[0]
            }
        }
        return false
    }

    isVisible(treeitem) {
        var flag = true
        if (this.isInSubtree(treeitem)) {
            treeitem = this.getParentTreeitem(treeitem)
            if (
                !treeitem ||
                treeitem.getAttribute('aria-expanded') === 'false'
            ) {
                return false
            }
        }
        return flag
    }

    isInSubtree(treeitem) {
        var parentNode = treeitem.closest('ul')
        if (parentNode) {
            return parentNode.getAttribute('role') === 'group'
        }
        return false
    }

    isExpandable(treeitem) {
        return treeitem.hasAttribute('aria-expanded')
    }

    isExpanded(treeitem) {
        return treeitem.getAttribute('aria-expanded') === 'true'
    }

    getVisibleTreeitems() {
        var items = []
        for (var i = 0; i < this.treeitems.length; i++) {
            var ti = this.treeitems[i]
            if (this.isVisible(ti)) {
                items.push(ti)
            }
        }
        return items
    }

    collapseTreeitem(treeitem) {
        if (treeitem.getAttribute('aria-owns')) {
            treeitem.click()
        }
    }

    expandTreeitem(treeitem) {
        if (treeitem.getAttribute('aria-owns')) {
            treeitem.click()
        }
    }

    expandAllSiblingTreeitems(treeitem) {
        var parentNode = treeitem.closest('ul')
        if (parentNode) {
            var siblingTreeitemNodes = parentNode.querySelectorAll(
                ':scope > li ' + this.triggerTag + '[aria-expanded]',
            )
            siblingTreeitemNodes.forEach((sibling) => {
                sibling.click()
            })
        }
    }

    setFocusToTreeitem(treeitem) {
        treeitem.focus()
    }

    setFocusToNextTreeitem(treeitem) {
        var visibleTreeitems = this.getVisibleTreeitems()
        var nextItem = false

        for (var i = visibleTreeitems.length - 1; i >= 0; i--) {
            var ti = visibleTreeitems[i]
            if (ti === treeitem) {
                break
            }
            nextItem = ti
        }
        if (nextItem) {
            this.setFocusToTreeitem(nextItem)
        }
    }

    setFocusToPreviousTreeitem(treeitem) {
        var visibleTreeitems = this.getVisibleTreeitems()
        var prevItem = false

        for (var i = 0; i < visibleTreeitems.length; i++) {
            var ti = visibleTreeitems[i]
            if (ti === treeitem) {
                break
            }
            prevItem = ti
        }

        if (prevItem) {
            this.setFocusToTreeitem(prevItem)
        }
    }

    setFocusToParentTreeitem(treeitem) {
        if (this.isInSubtree(treeitem)) {
            var parentNode = treeitem.closest('ul')
            var node = parentNode.previousElementSibling
            if (node && node.getAttribute('role') === 'treeitem') {
                // remove me
                this.setFocusToTreeitem(node)
                return
            }
            node = node.getElementsByTagName(this.triggerTag)
            if (node && node[0].getAttribute('role') === 'treeitem') {
                this.setFocusToTreeitem(node[0])
            }
        }
    }

    setFocusByFirstCharacter(treeitem, char) {
        var start,
            i,
            ti,
            index = -1
        var visibleTreeitems = this.getVisibleTreeitems()
        char = char.toLowerCase()

        // Get start index for search based on position of treeitem
        start = visibleTreeitems.indexOf(treeitem) + 1
        if (start >= visibleTreeitems.length) {
            start = 0
        }

        // Check remaining items in the tree
        for (i = start; i < visibleTreeitems.length; i++) {
            ti = visibleTreeitems[i]
            if (char === ti.textContent.trim()[0].toLowerCase()) {
                index = i
                break
            }
        }

        // If not found in remaining slots, check from beginning
        if (index === -1) {
            for (i = 0; i < start; i++) {
                ti = visibleTreeitems[i]
                if (char === ti.textContent.trim()[0].toLowerCase()) {
                    index = i
                    break
                }
            }
        }

        // If match was found...
        if (index > -1) {
            this.setFocusToTreeitem(visibleTreeitems[index])
        }
    }

    // Event handlers

    onKeydown(event) {
        var tgt = event.currentTarget,
            flag = false,
            key = event.key
        function isPrintableCharacter(str) {
            return str.length === 1 && str.match(/\S/)
        }

        if (event.altKey || event.ctrlKey || event.metaKey) {
            return
        }
        if (event.shift) {
            if (
                event.keyCode === this.keyCode.SPACE ||
                event.keyCode === this.keyCode.RETURN
            ) {
                event.stopPropagation()
            } else {
                if (isPrintableCharacter(key)) {
                    if (key === '*') {
                        this.expandAllSiblingTreeitems(tgt)
                        flag = true
                    } else {
                        this.setFocusByFirstCharacter(tgt, key)
                    }
                }
            }
        } else {
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
                    this.setFocusToPreviousTreeitem(tgt)
                    flag = true
                    break

                case 'Down':
                case 'ArrowDown':
                    this.setFocusToNextTreeitem(tgt)
                    flag = true
                    break

                case 'Right':
                case 'ArrowRight':
                    if (this.isExpandable(tgt)) {
                        if (this.isExpanded(tgt)) {
                            this.setFocusToNextTreeitem(tgt)
                        } else {
                            this.expandTreeitem(tgt)
                        }
                    }
                    flag = true
                    break

                case 'Left':
                case 'ArrowLeft':
                    if (this.isExpandable(tgt) && this.isExpanded(tgt)) {
                        this.collapseTreeitem(tgt)
                        flag = true
                    } else {
                        if (this.isInSubtree(tgt)) {
                            this.setFocusToParentTreeitem(tgt)
                            flag = true
                        }
                    }
                    break

                default:
                    if (isPrintableCharacter(key)) {
                        if (key === '*') {
                            this.expandAllSiblingTreeitems(tgt)
                            flag = true
                        } else {
                            this.setFocusByFirstCharacter(tgt, key)
                        }
                    }
                    break
            }
        }

        if (flag) {
            event.stopPropagation()
            event.preventDefault()
        }
    }
}

/**
 * ARIA Treeview example
 *
 * @function onload
 * @description  after page has loaded initialize all treeitems based on the role=treeitem
 */

document.addEventListener('DOMContentLoaded', function () {
    var trees = document.querySelectorAll('#section-tree [role="tree"]')
    for (let i = 0; i < trees.length; i++) {
        new TreeViewNavigation(trees[i])
    }
})
