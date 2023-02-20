/* global setSearchBarOnlySiteResources, $ */

function foldAllSubsections(){
    var container = $('#section-tree ul')
    $('ul',container).each(function () {
        $(this).addClass('d-none')
    })
    $('i.fold',container).each(function () {
        $(this).removeClass('rotate-90')
        $(this).addClass('rotate-0')
        $(this).attr('aria-expanded', 'false');
    })
}

function unfoldAllSubsections(){
    var container = $('#section-tree')
    $('ul',container).each(function () {
        $(this).removeClass('d-none')
    })
    $('i.fold',container).each(function () {
        $(this).addClass('rotate-90')
        $(this).removeClass('rotate-0')
        $(this).attr('aria-expanded', 'true');
    })
}

function setUpFoldAllButton() {
    if ($('#fold-all-tree').length === 0) {
        return;
    }
    let label
    $('#fold-all-tree').click(function () {
        // If click on button with "unfold" message
        if (this.getAttribute('aria-expanded') == "true"){
            foldAllSubsections()
            this.setAttribute('aria-expanded', 'false');
            label = this.dataset.labelExpand
        }
        else {
            unfoldAllSubsections()
            this.setAttribute('aria-expanded', 'true');
            label = this.dataset.labelCollapse
        }
        this.innerHTML = label
    })
}

function setupSearchBarFormArchivists() {
    const searchBarForm = document.querySelector('#search-bar-form')
    if (setSearchBarOnlySiteResources) {
        window.localStorage['FASiteSearchCategory'] = 'siteres'
        searchBarForm.rb1.checked = false
        searchBarForm.rb2.checked = true
    }
}


$('document').ready(function () {
    setUpFoldAllButton()
    setupSearchBarFormArchivists()
})
