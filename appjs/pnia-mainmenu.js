/*
 *   This content is licensed according to the W3C Software License at
 *   https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document
 *
 *   File: section-menu-navigation.js
 *   Desc: Tree item object for representing the state and user interactions for a
 *       tree widget for navigational links

 *   This software or document includes material copied from or
 *   derived from [Javascript: treeview-navigation.js and
 *   https://w3c.github.io/aria-practices/examples/treeview/js/treeview-navigation.js of the W3C document]. Copyright ©[YEAR] W3C® (MIT, ERCIM, Keio, Beihang).
 */

'use strict'

class SectionsMenuNavigation {
    constructor(node) {
        // Check whether node is a DOM element
        if (typeof node !== 'object') {
            console.error(
                "SectionsMenuNavigation: 'ul#sections-menu' element not found",
            )
            return
        }
        this.treeNode = node
        this.subtreeNode = document.getElementById('menu-subsection-container')
        if (typeof this.subtreeNode !== 'object') {
            console.error(
                "SectionsMenuNavigation: '#menu-subsection-container' element not found",
            )
            return
        }
        this.treeitems = this.treeNode.querySelectorAll('[role="treeitem"]')
        this.subsectionsNode = document.getElementById(
            'menu-subsection-container',
        )
        var subtreeitems =
            this.subsectionsNode.querySelectorAll('[role="treeitem"]')
        const allitems = Array.prototype.concat.call(
            ...this.treeitems,
            ...subtreeitems,
        )
        for (let i = 0; i < allitems.length; i++) {
            let ti = allitems[i]
            ti.addEventListener('keydown', this.onKeydown.bind(this))
            // first tree item is in tab sequence of page
            if (i === 0) {
                ti.tabIndex = 0
            } else {
                ti.tabIndex = -1
            }
        }
        const control = this
        // setup drop

        var menu = document.getElementById('main-menu'),
            menu_panel = document.getElementById('menu-panel'),
            button = document.getElementById('menu-toggle'),
            items = this.treeNode.querySelectorAll('#menu-panel a')

        menu.addEventListener('keydown', function (e) {
            if (!items.length) return
            // no menu to open
            if (e.key !== 'Enter') return
            e.preventDefault()
            e.stopPropagation()
            button.click()
        })

        button.addEventListener('click', function () {
            menu_panel.classList.toggle('hidden')
            if (menu_panel.classList.contains('hidden')) {
                control.hideAllSectionPanels()
                control.unFocusAllSections()
            }
            this.classList.toggle('open')
            document.getElementById('menu-icon').classList.toggle('open')
            if (this.classList.contains('open')) {
                menu.setAttribute('aria-expanded', 'true')
                items[0].focus()
            } else {
                menu.setAttribute('aria-expanded', 'false')
            }
        })
        // setup menu panel
        this.treeNode
            .querySelectorAll('#menu-panel .panel-section [aria-owns]')
            .forEach(function (treeitem) {
                treeitem.addEventListener('mouseover', function () {
                    control.openSiteMenuPanel(treeitem)
                })
            })

        //setup subsections descriptions
        this.subtreeNode
            .querySelectorAll('.menu-subsection-item')
            .forEach(function (item) {
                item.addEventListener('mouseenter', function () {
                    // hide all subsection descriptions
                    control.hideAllSubsectionDescriptions(item)
                })
                item.addEventListener('mouseleave', function () {
                    var desc = document.getElementById(
                        item.id.replace('subsection', 'description'),
                    )
                    if (desc) {
                        desc.classList.add('hidden')
                    }
                })
            })
        subtreeitems.forEach(function (item) {
            item.addEventListener('focus', function () {
                // hide all subsection descriptions
                this.parentNode.dispatchEvent(new Event('mouseenter'))
            })
            item.addEventListener('blur', function () {
                // hide the current subsection descriptions
                this.parentNode.dispatchEvent(new Event('mouseleave'))
            })
        })
    }

    hideAllSubsectionDescriptions(div) {
        if (!div) return
        var desc = document.getElementById(
            div.id.replace('subsection', 'description'),
        )
        this.treeNode
            .querySelectorAll('.subsection-description')
            .forEach(function (desc) {
                if (desc.classList.contains('hidden')) return
                desc.classList.add('hidden')
            })
        //show only current subsection description
        if (desc) {
            desc.classList.remove('hidden')
        }
    }

    hideAllSectionPanels() {
        this.subtreeNode
            .querySelectorAll('.menu-panel-section')
            .forEach(function (section) {
                if (section.classList.contains('hidden')) return
                section.classList.add('hidden')
            })
    }

    unFocusAllSections() {
        this.treeNode
            .querySelectorAll('.panel-section')
            .forEach(function (section) {
                section.classList.remove('open')
                var link = section.getElementsByTagName('a')
                if (link !== undefined && link.length > 0) {
                    link[0].setAttribute('aria-expanded', 'false')
                }
            })
    }

    openSiteMenuPanel(treeitem) {
        this.hideAllSectionPanels()
        // Show only pannel corresponding to current section
        document
            .getElementById(treeitem.getAttribute('aria-owns'))
            .classList.toggle('hidden')
        //remove all open class from sections
        this.unFocusAllSections()
        treeitem.parentNode.classList.add('open')
        treeitem.setAttribute('aria-expanded', 'true')
    }

    getParentTreeitemSectionNode(treeitem) {
        var node = treeitem.closest("div[role='group']")
        if (node) {
            return document.getElementById(node.id.replace('section', 'panel'))
        }
        return false
    }

    isVisible(treeitem) {
        var flag = true
        if (this.isInSubtree(treeitem)) {
            var sectionNode = this.getParentTreeitemSectionNode(treeitem)
            if (
                !sectionNode ||
                sectionNode.getAttribute('aria-expanded') === 'false'
            ) {
                return false
            }
        }
        return flag
    }

    isInSubtree(treeitem) {
        var parentNode = treeitem.closest("div[role='group']")
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

    getTreeItemSiblings(treeitem) {
        var parent = treeitem.closest("div[role='group']")
        if (parent) {
            return parent.querySelectorAll('[role="treeitem"]')
        }
        return []
    }

    getVisibleTreeitems(treeitem) {
        var treeitems
        if (treeitem.getAttribute('aria-owns')) {
            var tree = document.getElementById(
                treeitem.getAttribute('aria-owns'),
            )
            treeitems = tree.querySelectorAll('ul [role="treeitem"]')
        } else {
            treeitems = this.getTreeItemSiblings(treeitem)
        }
        var items = []
        for (var i = 0; i < treeitems.length; i++) {
            var ti = treeitems[i]
            if (this.isVisible(ti)) {
                items.push(ti)
            }
        }
        return items
    }

    expandTreeitem(treeitem) {
        if (treeitem.getAttribute('aria-owns')) {
            this.openSiteMenuPanel(treeitem)
        }
    }

    setFocusToTreeitem(treeitem) {
        treeitem.focus()
    }

    setFocusToNextTreeitem(treeitem) {
        var visibleTreeitems = this.getVisibleTreeitems(treeitem)
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

    setFocusToNextSection(treeitem) {
        var visibleTreeitems = this.treeitems
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
            if (this.isExpanded(treeitem)) {
                // enxpand nextItem
                this.expandTreeitem(nextItem)
            }
        }
    }

    setFocusToPreviousTreeitem(treeitem) {
        var visibleTreeitems = this.getVisibleTreeitems(treeitem)
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
            //this.hideAllSubsectionDescriptions(prevItem.parentNode)
        } else {
            //try to get to the parent section
            if (!this.isExpandable(treeitem)) {
                this.setFocusToParentTreeitem(treeitem)
            }
        }
    }

    setFocusToPreviousSection(treeitem) {
        var visibleTreeitems = this.treeitems
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
            if (this.isExpanded(treeitem)) {
                // enxpand prevItem
                this.expandTreeitem(prevItem)
            }
        }
    }

    setFocusToParentTreeitem(treeitem) {
        var parent = this.getParentTreeitemSectionNode(treeitem)
        if (parent) {
            this.setFocusToTreeitem(parent.querySelectorAll('[aria-owns]')[0])
        }
    }

    setFocusByFirstCharacter(treeitem, char) {
        var start,
            i,
            ti,
            index = -1
        var visibleTreeitems = this.getVisibleTreeitems(treeitem)
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
                    if (key !== '*') {
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
                    if (!this.isExpandable(tgt)) {
                        this.setFocusToPreviousTreeitem(tgt)
                    }
                    flag = true
                    break

                case 'Down':
                case 'ArrowDown':
                    if (this.isExpandable(tgt)) {
                        if (this.isExpanded(tgt)) {
                            this.setFocusToNextTreeitem(tgt)
                        } else {
                            this.expandTreeitem(tgt)
                        }
                    } else {
                        // navigation by siblings
                        this.setFocusToNextTreeitem(tgt)
                    }
                    flag = true
                    break

                case 'Right':
                case 'ArrowRight':
                    if (this.isExpandable(tgt)) {
                        this.setFocusToNextSection(tgt)
                    } else {
                        this.setFocusToParentTreeitem(tgt)
                    }
                    flag = true
                    break

                case 'Left':
                case 'ArrowLeft':
                    if (this.isExpandable(tgt)) {
                        this.setFocusToPreviousSection(tgt)
                    } else {
                        this.setFocusToParentTreeitem(tgt)
                    }
                    flag = true
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
 * ARIA for #sections-menu (menu-first-level)
 *
 * @function onload
 * @description  after page has loaded initialize ul.menu-first-level tree
 */

document.addEventListener(
    'DOMContentLoaded',
    () => new SectionsMenuNavigation(document.getElementById('sections-menu')),
)
