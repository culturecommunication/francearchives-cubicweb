/*
 * Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2022
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

import React, {useEffect, useState} from 'react'
import {AsyncTypeahead} from 'react-bootstrap-typeahead'
import {
    SearchRequest,
    QueryDslBoolQuery,
} from '@elastic/elasticsearch/lib/api/types'
import {translate as t} from '../translate'

const TYPE_ES = {
    a: 'AgentAuthority',
    l: 'LocationAuthority',
    s: 'SubjectAuthority',
}

export function AuthorityTypeAhead({
    archivesRef,
    ressourcesSite,
    endpoint,
    selectedMemory,
    update,
    typeaheadId,
    type,
    clearNow,
    setClearNow,
}) {
    const [isLoading, setIsLoading] = useState(false)
    const [options, setOptions] = useState(selectedMemory)
    const [selected, setSelected] = useState(selectedMemory)
    const [errorMsg, setErrorMsg] = React.useState<string | null>()
    useEffect(() => {
        if (clearNow) {
            setSelected([{eid: '', label: ''}])
            setClearNow(false)
        }
    }, [clearNow])

    const handleSearch = (textSearch) => {
        setIsLoading(true)
        // TODO: remove accents ?
        let must: QueryDslBoolQuery['must'] = [
            {match: {cw_etype: TYPE_ES[type]}},
            {
                multi_match: {
                    query: textSearch,
                    operator: 'and',
                    type: 'bool_prefix', // look for terms starting by textSearch
                    fields: ['label', 'label._2gram', 'label._3gram'],
                },
            },
        ]
        let countAttr = 'count'
        if (archivesRef && !ressourcesSite) {
            countAttr = 'archives'
            must.push({range: {archives: {gte: 1}}})
        } else if (!archivesRef && ressourcesSite) {
            countAttr = 'siteres'
            must.push({range: {siteres: {gte: 1}}})
        } else {
            must.push({range: {count: {gte: 1}}})
        }

        const es_query: SearchRequest = {
            query: {
                bool: {
                    must: must,
                    should: [
                        // give a better score if textSearch strictly matches an authority name
                        {
                            match_phrase: {
                                'text.raw': {
                                    query: textSearch,
                                    boost: 10,
                                    slop: 2,
                                },
                            },
                        },
                        // give a better score if the whole name starts with textSearch
                        {
                            match_bool_prefix: {
                                'text.raw': {query: textSearch},
                            },
                        },
                    ],
                },
            },
            sort: ['_score'],
            from: 0,
            size: 100,
        }
        fetch(`${endpoint}`, {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(es_query),
        })
            .then((resp) => {
                return resp.json()
            })
            .then((response) => {
                if (response.errors !== undefined) {
                    setErrorMsg(response.errors[0].details)
                    setOptions([])
                } else {
                    setErrorMsg(null)
                    const items = response['hits']['hits'].map((element) => {
                        let count = element['_source'][countAttr]
                        return {
                            eid: element['_source']['eid'],
                            label: element['_source']['text'],
                        }
                    })
                    setOptions(items)
                }
                setIsLoading(false)
            })
            .catch((error) => {
                console.error(error)
            })
    }
    const filterBy = () => true
    const hasError = errorMsg !== undefined && errorMsg !== null
    return (
        <>
            {hasError ? (
                <div className="invalid-feedback">{errorMsg}</div>
            ) : null}
            <AsyncTypeahead
                clearButton
                filterBy={filterBy}
                id={typeaheadId}
                isLoading={isLoading}
                labelKey="label"
                minLength={3}
                onSearch={handleSearch}
                options={options}
                onChange={(selectedElement) => {
                    if (selectedElement.length == 1) {
                        update({
                            value: selectedElement[0].eid,
                            label: selectedElement[0].label,
                        })
                    } else {
                        //Nothing is selected
                        update({value: '', label: ''})
                    }
                    setSelected(selectedElement)
                }}
                selected={selected}
                className={hasError ? 'is-invalid' : ''}
                useCache={false}
            />
        </>
    )
}
