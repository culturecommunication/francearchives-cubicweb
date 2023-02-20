import React, {Fragment, useState} from 'react'
import Button from 'react-bootstrap/Button'
import InputGroup from 'react-bootstrap/InputGroup'

import {YearInput} from './widgets'
import {translate as t} from '../translate'

export function DatesBox({minDate, setMinDate, maxDate, setMaxDate}) {
    const [periodInput, setPeriodInput] = useState(minDate != maxDate)

    return (
        <Fragment>
            <h2>{t('Dates')}</h2>
            <InputGroup className="mb-3">
                <Button
                    onClick={() => {
                        setPeriodInput(false)
                        setMaxDate(minDate)
                    }}
                    active={!periodInput}
                    variant="as-date-exacte"
                >
                    {t('Year')}
                </Button>
                <Button
                    onClick={() => setPeriodInput(true)}
                    active={periodInput}
                    variant="as-date-period"
                >
                    {t('Period')}
                </Button>
                {!periodInput ? (
                    <YearInput
                        id="as-exact-date"
                        label={t('Exact year')}
                        value={minDate}
                        setValue={(value) => {
                            setMinDate(value)
                            setMaxDate(value)
                        }}
                        minValue={false}
                    />
                ) : (
                    <>
                        <YearInput
                            id="as-min-date"
                            label={t('Start year')}
                            value={minDate}
                            setValue={setMinDate}
                            minValue={false}
                        />
                        <YearInput
                            id="as-max-date"
                            label={t('Stop year')}
                            value={maxDate}
                            setValue={setMaxDate}
                            minValue={minDate}
                        />
                    </>
                )}
            </InputGroup>
        </Fragment>
    )
}
