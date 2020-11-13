/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2019
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

/* global data */

import {render} from 'react-dom'
import {Component, createElement as ce} from 'react'

import {BootstrapTable, TableHeaderColumn} from 'react-bootstrap-table'

function titleFormat(cell) {
    return ce('a', {href: cell[1]}, cell[0])
}

function statusFormat(cell) {
    return ce('div', {
        className: `circular-status circular-status-${cell[1]} circular-status--block`,
        title: cell[0],
    })
}

function caretRender(direction) {
    const carets = []
    let selected = false
    if (direction === 'asc') {
        selected = true
        carets.push(ce('i', {className: 'fa fa-caret-up'}))
    } else if (direction === 'desc') {
        selected = true
        carets.push(ce('i', {className: 'fa fa-caret-down'}))
    } else {
        carets.push(
            ce('i', {className: 'fa fa-caret-up'}),
            ce('i', {className: 'fa fa-caret-down'}),
        )
    }
    return ce(
        'span',
        {
            className: `circulartable_caret ${
                selected ? 'circulartable_caret-selected' : ''
            }`,
        },
        ...carets,
    )
}

const ALL_BUSINESS_FIELDS_DEFAULT = '-- tous --'
const ALL_BUSINESS_FIELDS = [ALL_BUSINESS_FIELDS_DEFAULT].concat(
    Array.from(
        new Set(
            data.reduce((acc, value) => acc.concat(value.business_fields), []),
        ),
    ).sort(),
)
const ALL_BUSINESS_FIELDS_OPTIONS = ALL_BUSINESS_FIELDS.map((b, idx) =>
    ce('option', {key: `bfield-${idx}`, value: b}, b),
)

class CircularTable extends Component {
    constructor(props) {
        super(props)
        this.state = {
            selectedData: data,
            selectedBF: ALL_BUSINESS_FIELDS_DEFAULT,
        }
        this.updateBF = this.updateBF.bind(this)
    }

    updateBF(ev) {
        ev.preventDefault()
        const selectedBF = ev.target.value
        this.setState({
            selectedBF,
            selectedData:
                selectedBF === ALL_BUSINESS_FIELDS_DEFAULT
                    ? data
                    : data.filter((d) =>
                          d.business_fields.includes(selectedBF),
                      ),
        })
    }

    render() {
        const {selectedBF, selectedData} = this.state
        return ce(
            'div',
            null,
            ce('span', null, 'Sélectionner un domaine (thésaurus) : '),
            ce(
                'select',
                {value: selectedBF, onChange: this.updateBF},
                ALL_BUSINESS_FIELDS_OPTIONS,
            ),
            ce(
                BootstrapTable,
                {
                    data: selectedData,
                    striped: true,
                    hover: true,
                    pagination: true,
                    search: true,
                    searchPlaceholder: 'rechercher',
                    options: {
                        defaultSortOrder: 'desc',
                        defaultSortName: 'date',
                        sizePerPage: selectedData.length,
                        sizePerPageList: [
                            {
                                text: '10',
                                value: 10,
                            },
                            {
                                text: '50',
                                value: 50,
                            },
                            {
                                text: '100',
                                value: 100,
                            },
                            {
                                text: `tout (${selectedData.length})`,
                                value: selectedData.length,
                            },
                        ],
                    },
                },
                ce(TableHeaderColumn, {
                    isKey: true,
                    dataField: 'eid',
                    hidden: true,
                }),
                ce(
                    TableHeaderColumn,
                    {
                        dataField: 'kind',
                        with: '10%',
                        dataSort: true,
                        caretRender,
                    },
                    'Nature',
                ),
                ce(
                    TableHeaderColumn,
                    {
                        dataField: 'code',
                        with: '10%',
                        dataSort: true,
                        caretRender,
                    },
                    'Code',
                ),
                ce(
                    TableHeaderColumn,
                    {
                        dataField: 'date',
                        with: '10%',
                        dataSort: true,
                        caretRender,
                        dataFormat(cell) {
                            if (!cell) {
                                return
                            }
                            const [year, month, day] = cell.split('-')
                            return `${day}/${month}/${year}`
                        },
                    },
                    'Date',
                ),
                ce(
                    TableHeaderColumn,
                    {dataField: 'title', dataFormat: titleFormat, width: '65%'},
                    'Titre',
                ),
                ce(
                    TableHeaderColumn,
                    {
                        dataField: 'status',
                        dataFormat: statusFormat,
                        width: '5%',
                    },
                    'Statut',
                ),
            ),
        )
    }
}

render(ce(CircularTable), document.getElementById('bs-table-container'))
