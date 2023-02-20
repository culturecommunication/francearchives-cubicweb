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

import React, {useState, useEffect} from 'react'
import {
    SearchRequest,
    QueryDslBoolQuery,
} from '@elastic/elasticsearch/lib/api/types'
import {DropDown, PlusButton, RemoveRowButton} from './widgets'
import {AsyncTypeahead} from 'react-bootstrap-typeahead'
import {translate as t} from '../translate'

export function ServiceTypeAhead({
    archivesRef,
    ressourcesSite,
    update,
    selectedMemory,
    typeaheadId,
    clearNow,
    setClearNow,
    endpoint,
    placeholder,
}) {
    const [isLoading, setIsLoading] = useState(false)
    const [options, setOptions] = useState(selectedMemory)
    const [selected, setSelected] = useState(selectedMemory)
    const [errorMsg, setErrorMsg] = React.useState<string | null>()
    const handleSearch = (textSearch) => {
        setIsLoading(true)
        let must: QueryDslBoolQuery['must'] = [
            {
                simple_query_string: {
                    query: `${textSearch}*`,
                    fields: ['short_name^3', 'alltext'],
                    default_operator: 'and',
                },
            },
        ]
        let countAttr = 'documents_count'
        if (archivesRef && !ressourcesSite) {
            countAttr = 'archives'
            must.push({range: {archives: {gte: 1}}})
        } else if (!archivesRef && ressourcesSite) {
            countAttr = 'siteres'
            must.push({range: {siteres: {gte: 1}}})
        } else {
            must.push({range: {documents_count: {gte: 1}}})
        }

        const es_query: SearchRequest = {
            query: {
                bool: {
                    must: must,
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
                    const items = response['hits']['hits']
                        .map((element) => {
                            return {
                                eid: element['_source']['eid'],
                                label:
                                    element['_source']['short_name'] ||
                                    element['_source']['title'],
                            }
                        })
                        .filter((element) => {
                            return element['label'] !== null
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
    useEffect(() => {
        if (clearNow) {
            setSelected([{eid: '', label: ''}])
            setClearNow(false)
        }
    }, [clearNow])
    return (
        <>
            {hasError ? (
                <div className="invalid-feedback">{errorMsg}</div>
            ) : null}
            <AsyncTypeahead
                filterBy={filterBy}
                clearButton
                id={typeaheadId}
                isLoading={isLoading}
                labelKey="label"
                minLength={2}
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
                className={hasError ? 'is-invalid' : ''}
                selected={selected}
                useCache={false}
                placeholder={placeholder}
            />
        </>
    )
}

export function ServicesBox({
    searches,
    labels,
    addSearch,
    updateSearch,
    operator,
    setOperator,
    endpoint,
    clearNow,
    setClearNow,
    removeService,
    ressourcesSite,
    archivesRef,
}) {
    return (
        <>
            <h2>{t('Publisher')}</h2>
            <>
                <DropDown
                    value={operator}
                    choices={['OU', 'SAUF']}
                    labels={{OU: t('Include'), SAUF: t('Exclude')}}
                    update={(value) => {
                        setOperator(value)
                    }}
                    help={`"Sélectionner une condition pour le champ Service`}
                    variant="as-operators-service"
                />
                {searches.map((element, index) => (
                    <div key={`service${index}`} className="mb-3">
                        <div className="row">
                            <div className="col-lg-10 mb-3 input-search">
                                <ServiceTypeAhead
                                    update={(value) =>
                                        updateSearch(value, index)
                                    }
                                    selectedMemory={[
                                        {eid: element, label: labels[index]},
                                    ]}
                                    typeaheadId={`service-typeahead-${index}`}
                                    endpoint={endpoint}
                                    clearNow={clearNow}
                                    setClearNow={setClearNow}
                                    placeholder={t('Archive service')}
                                    ressourcesSite={ressourcesSite}
                                    archivesRef={archivesRef}
                                />
                            </div>
                            <div className="col-lg-2 mb-3">
                                {index == searches.length - 1 ? (
                                    <PlusButton onClick={addSearch} />
                                ) : (
                                    <></>
                                )}
                                {index > 0 ? (
                                    <RemoveRowButton
                                        onClick={() => {
                                            removeService(index)
                                        }}
                                    />
                                ) : (
                                    <></>
                                )}
                            </div>
                        </div>
                    </div>
                ))}
            </>
        </>
    )
}
