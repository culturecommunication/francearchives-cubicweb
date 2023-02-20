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
import Form from 'react-bootstrap/Form'
import Button from 'react-bootstrap/Button'
import Dropdown from 'react-bootstrap/Dropdown'
import DropdownButton from 'react-bootstrap/DropdownButton'
import {translate as t} from '../translate'

export interface ICheckbox {
    label: string
    value: boolean
    toggleFunction: () => void
    className?: string
}

export function Checkbox({label, value, toggleFunction, className}: ICheckbox) {
    return (
        <Form.Check inline type="checkbox" className={className}>
            <Form.Check.Input
                type="checkbox"
                checked={value}
                onChange={toggleFunction}
            />
            <Form.Check.Label>{label}</Form.Check.Label>
        </Form.Check>
    )
}

export interface ITextInput {
    value: string
    setFunction: (input: string) => void
}

export function TextInput({setFunction, value}: ITextInput) {
    return (
        <Form.Control
            value={value}
            onChange={(e) => setFunction(e.target.value)}
            type="text"
        />
    )
}

export interface IPlusButton {
    onClick: () => void
}

export function PlusButton({onClick}: IPlusButton) {
    return (
        <Button
            onClick={onClick}
            variant="as-plus"
            title={t('Add a criterion')}
            aria-label={t('Add a criterion')}
        >
            +
        </Button>
    )
}

export interface IRemoveRowButton {
    onClick: () => void
}

export function RemoveRowButton({onClick}: IRemoveRowButton) {
    return (
        <Button
            onClick={onClick}
            variant="as-remove"
            title={t('Remove a criterion')}
            aria-label={t('Remove a criterion')}
        >
            -
        </Button>
    )
}

export function DropDown({
    value,
    choices,
    labels,
    update,
    variant,
    help,
    onValueChange = () => {},
}) {
    return (
        <DropdownButton
            title={labels[value]}
            variant={variant}
            arial-label={help}
        >
            {choices.map((choice, index) => (
                <Dropdown.Item
                    key={choice}
                    onClick={() => {
                        if (choice !== value) {
                            onValueChange()
                        }
                        update(choice)
                    }}
                >
                    {labels[choice]}
                </Dropdown.Item>
            ))}
        </DropdownButton>
    )
}

export function YearInput({id, label, value, setValue, minValue}) {
    const [invalid, setInvalid] = useState(false)
    const [aboveMin, setAboveMin] = useState(value < minValue)
    useEffect(() => {
        if (minValue && value && value < minValue) {
            setAboveMin(true)
        } else {
            setAboveMin(false)
        }
    }, [minValue, value])

    const checkNumberOrNull = (input) => {
        if (!isNaN(parseInt(input))) {
            setValue(parseInt(input))
            setInvalid(false)
        } else if (input === '') {
            setValue(null)
            setInvalid(false)
        } else {
            setValue(null)
            setInvalid(true)
        }
    }
    return (
        <>
            <Form.Group className="as-dates">
                {invalid ? (
                    <Form.Control.Feedback type="invalid">
                        Saisie doit être un nombre
                    </Form.Control.Feedback>
                ) : (
                    <></>
                )}
                {aboveMin ? (
                    <Form.Control.Feedback type="invalid">
                        La date de fin doit être supérieure à la date de début
                    </Form.Control.Feedback>
                ) : (
                    <></>
                )}

                <Form.Control
                    id={id}
                    placeholder={label}
                    value={value ?? ''}
                    onChange={(e) => checkNumberOrNull(e.target.value)}
                    onFocus={() => {
                        setInvalid(false)
                    }}
                    onBlur={() => {
                        setInvalid(false)
                    }}
                    isInvalid={invalid || aboveMin}
                    aria-label={label}
                />
            </Form.Group>
        </>
    )
}
