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

import React, {useState} from 'react'
import {AuthorityTypeAhead} from './authoritySearchBar'
import {DropDown, PlusButton, RemoveRowButton, TextInput} from './widgets'
import {translate as t} from '../translate'

const TYPE_LABELS = {
    t: t('Plain text'),
    l: t('Location'),
    a: t('Person or institution'),
    s: t('Topic'),
}

export function TextOrAuthorityInput({
    archivesRef,
    ressourcesSite,
    value,
    type,
    label,
    update,
    updateType,
    endpoint,
    index,
    operators,
    updateOperator,
    addSearch,
    removeSearch,
}) {
    const helpLabel = t('Select criterion for the field')
    const [clearNow, setClearNow] = useState(false)
    return (
        <>
            <div className="row">
                <DropDown
                    value={type}
                    choices={Object.keys(TYPE_LABELS)}
                    labels={TYPE_LABELS}
                    update={updateType}
                    variant="as-scope"
                    help={`#${helpLabel} #${index}`}
                    onValueChange={() => {
                        update({value: '', label: ''})
                        setClearNow(true)
                    }}
                />
            </div>
            <div className="row">
                <div className="col-lg-10 mb-3 input-search">
                    {type === 't' ? (
                        <TextInput
                            value={value}
                            setFunction={(value) => {
                                update({value: value, label: ''})
                            }}
                        />
                    ) : (
                        <div>
                            <AuthorityTypeAhead
                                archivesRef={archivesRef}
                                ressourcesSite={ressourcesSite}
                                endpoint={endpoint}
                                selectedMemory={[{eid: value, label: label}]}
                                update={update}
                                typeaheadId={`authority-typeahead-${index}`}
                                type={type}
                                clearNow={clearNow}
                                setClearNow={setClearNow}
                            />
                        </div>
                    )}
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
                        <RemoveRowButton onClick={removeSearch} />
                    ) : (
                        <></>
                    )}
                </div>
            </div>
        </>
    )
}

export function TextOrAuthoritySearchBox({
    archivesRef,
    ressourcesSite,
    searches,
    addSearch,
    updateSearch,
    operators,
    updateOperator,
    searchTypes,
    updateSearchType,
    labels,
    endpoint,
    removeSearch,
}) {
    return (
        <>
            <h2>{t('By word')}</h2>
            {searches.map((element, index) => (
                <div key={`search${index}`} id={`as-toasb-${index}`}>
                    <TextOrAuthorityInput
                        archivesRef={archivesRef}
                        ressourcesSite={ressourcesSite}
                        value={element}
                        type={searchTypes[index]}
                        label={labels[index]}
                        update={(value) => {
                            updateSearch(value, index)
                        }}
                        updateType={(value) => {
                            updateSearchType(value, index)
                        }}
                        endpoint={endpoint}
                        index={index}
                        operators={operators}
                        updateOperator={updateOperator}
                        addSearch={addSearch}
                        removeSearch={() => {
                            removeSearch(index)
                        }}
                    />
                </div>
            ))}
        </>
    )
}
