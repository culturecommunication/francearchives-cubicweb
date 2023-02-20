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
import ReactDOM from 'react-dom'

import Button from 'react-bootstrap/Button'
import {Checkbox} from './widgets'
import {TextOrAuthoritySearchBox} from './textOrAuthorityBox'
import {useAdvancedSearch} from './useAdvancedSearch'
import {ServicesBox} from './servicesBox'
import {ProducerBox} from './producerBox'
import {DatesBox} from './datesBox'
import InputGroup from 'react-bootstrap/InputGroup'
import {translate as t} from '../translate'

function AdvancedSearch() {
    const [loading, setLoading] = useState(true)
    const {
        archivesRef,
        toggleArchivesRef,
        ressourcesSite,
        toggleRessourcesSite,
        searches,
        addSearch,
        updateSearch,
        removeSearch,
        operators,
        updateOperator,
        authoritiesLabels,
        searchTypes,
        updateSearchType,
        services,
        addService,
        updateService,
        removeService,
        serviceOperator,
        setServiceOperator,
        servicesLabels,
        producers,
        addProducer,
        updateProducer,
        removeProducer,
        producerOperators,
        updateProducerOperator,
        updateProducerType,
        minDate,
        setMinDate,
        maxDate,
        setMaxDate,
        launchSearch,
        loadSessionStorage,
        resetValues,
        clearServicesNow,
        setClearServicesNow,
        clearProducersNow,
        setClearProducersNow,
    } = useAdvancedSearch()

    useEffect(() => {
        loadSessionStorage()
        setLoading(false)
    }, [])

    if (loading) {
        return <span>Loading....</span>
    }
    return (
        <>
            <h1>{t('Advanced search')}</h1>
            <div className="fluid-container">
                <div className="float-end">
                    <Button
                        variant="as-send"
                        onClick={launchSearch}
                        type="submit"
                    >
                        {t('Launch the search')}
                    </Button>
                    <Button onClick={() => resetValues()} variant="as-refresh">
                        <i className="fa fa-refresh"></i>
                        {t('Reset search')}
                    </Button>
                </div>
                <div className="clearfix" />
                <div className="as-field mt-5">
                    <h2>{t('Type of resources')}</h2>
                    <InputGroup className="mb-3">
                        <Checkbox
                            label={t('Referenced archives')}
                            value={archivesRef}
                            toggleFunction={() => {
                                toggleArchivesRef()
                                resetValues(false)
                            }}
                        />
                        <Checkbox
                            label={t('Site contents')}
                            value={ressourcesSite}
                            toggleFunction={() => {
                                toggleRessourcesSite()
                                resetValues(false)
                            }}
                        />{' '}
                    </InputGroup>
                </div>
                <div className="as-field">
                    <TextOrAuthoritySearchBox
                        archivesRef={archivesRef}
                        ressourcesSite={ressourcesSite}
                        searches={searches}
                        addSearch={addSearch}
                        updateSearch={updateSearch}
                        operators={operators}
                        updateOperator={updateOperator}
                        searchTypes={searchTypes}
                        updateSearchType={updateSearchType}
                        labels={authoritiesLabels}
                        endpoint={'advanced_search/suggest'}
                        removeSearch={removeSearch}
                    />
                </div>
                <div className="as-field">
                    <ServicesBox
                        searches={services}
                        labels={servicesLabels}
                        addSearch={addService}
                        updateSearch={updateService}
                        operator={serviceOperator}
                        setOperator={setServiceOperator}
                        endpoint={'advanced_search/services'}
                        clearNow={clearServicesNow}
                        setClearNow={setClearServicesNow}
                        removeService={removeService}
                        archivesRef={archivesRef}
                        ressourcesSite={ressourcesSite}
                    />
                </div>
                {archivesRef ? (
                    <div className="as-field">
                        <ProducerBox
                            searches={producers}
                            addSearch={addProducer}
                            updateSearch={updateProducer}
                            operators={producerOperators}
                            updateOperator={updateProducerOperator}
                            updateType={updateProducerType}
                            endpoint={'advanced_search/all'}
                            clearNow={clearProducersNow}
                            setClearNow={setClearProducersNow}
                            removeSearch={removeProducer}
                        />
                    </div>
                ) : (
                    <></>
                )}
                <div className="as-field mb-4">
                    <DatesBox
                        minDate={minDate}
                        setMinDate={setMinDate}
                        maxDate={maxDate}
                        setMaxDate={setMaxDate}
                    />
                </div>

                <div className="float-end">
                    <Button
                        variant="as-send"
                        onClick={launchSearch}
                        type="submit"
                    >
                        {t('Launch the search')}
                    </Button>
                    <Button onClick={() => resetValues()} variant="as-refresh">
                        <i className="fa fa-refresh"></i>
                        {t('Reset search')}
                    </Button>
                </div>
                <div className="clearfix" />
            </div>
        </>
    )
}

const root = document.getElementById('advanced-search')
ReactDOM.render(<AdvancedSearch />, root)
