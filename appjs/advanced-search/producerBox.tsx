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
 * modify and redistribute granted by the licens, users are provided only
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

import React, {useState, useEffect, useCallback} from 'react'
import {DropDown, PlusButton, RemoveRowButton} from './widgets'
import {AsyncTypeahead} from 'react-bootstrap-typeahead'
import {translate as t} from '../translate'

export function ProducerTypeAhead({
    endpoint,
    selected,
    update,
    updateType,
    typeaheadId,
    clearNow,
    setClearNow,
    placeholder,
}) {
    const [isLoading, setIsLoading] = useState(false)
    const [options, setOptions] = useState([])
    const [errorMsg, setErrorMsg] = React.useState<string | null>()

    useEffect(() => {
        if (clearNow) {
            update('')
            setClearNow(false)
        }
    }, [clearNow])

    const handleSearch = useCallback((textSearch) => {
        if (textSearch.length < 3) {
            return
        }

        setIsLoading(true)
        // TODO: remove accents

        const es_query = {
            query: {
                simple_query_string: {
                    query: `${textSearch}*`,
                    fields: ['originators.text'],
                    default_operator: 'and',
                },
            },
            size: 0,
            aggs: {
                producer: {
                    terms: {field: 'originators', size: 30},
                },
            },
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
                    const items = response['aggregations']['producer'][
                        'buckets'
                    ].map((element) => element['key'])
                    setOptions(items)
                }
                setIsLoading(false)
            })
            .catch((error) => {
                console.error(error)
            })
    }, [])
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
                onSearch={handleSearch}
                options={options}
                minLength={0}
                onInputChange={(value, event) => {
                    update(value)
                    updateType('t')
                }}
                onChange={(selectedElement) => {
                    if (selectedElement.length === 1) {
                        update(selectedElement[0])
                        updateType('k')
                    } else {
                        updateType('t')
                    }
                }}
                className={hasError ? 'is-invalid' : ''}
                selected={selected === '' ? [] : [selected]}
                placeholder={placeholder}
            />
        </>
    )
}

export function ProducerBox({
    searches,
    addSearch,
    updateSearch,
    operators,
    updateOperator,
    updateType,
    endpoint,
    clearNow,
    setClearNow,
    removeSearch,
}) {
    const helpLabel = t('Select criterion for the field')
    return (
        <>
            <h2>{t("Record's creator")}</h2>
            {searches.map((element, index) => (
                <div key={`authority${index}`} className="mb-3">
                    <div className="row">
                        <div className="col-lg-10 mb-3 input-search">
                            <ProducerTypeAhead
                                endpoint={endpoint}
                                selected={element}
                                update={(value) => updateSearch(value, index)}
                                updateType={(value) => updateType(value, index)}
                                typeaheadId={`producer-typeahead-${index}`}
                                clearNow={clearNow}
                                setClearNow={setClearNow}
                                placeholder="Producteur d'archives"
                            />
                        </div>
                        <div className="col-lg-2 mb-3">
                            {operators.length > index ? (
                                <DropDown
                                    value={operators[index]}
                                    choices={['ET', 'OU', 'SAUF']}
                                    labels={{
                                        ET: t('AND'),
                                        OU: t('OR'),
                                        SAUF: t('EXCEPT'),
                                    }}
                                    update={(value) => {
                                        updateOperator(value, index)
                                    }}
                                    help={`#${helpLabel} #${index}`}
                                    variant="as-operators"
                                />
                            ) : (
                                <PlusButton onClick={addSearch} />
                            )}
                            {index > 0 ? (
                                <RemoveRowButton
                                    onClick={() => {
                                        removeSearch(index)
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
    )
}
