type TranslationsDict = {
    [msg: string]: string
}

declare global {
    interface Window {
        TRANSLATIONS?: TranslationsDict
    }
}

function translate(msg: string, ...args: any[]): string {
    if (typeof msg === 'undefined') {
        // eslint-disable-next-line no-console
        console.error('undefined string to translate!')
        return ''
    }
    if (typeof window.TRANSLATIONS === 'undefined') {
        window.TRANSLATIONS = {}
    }

    msg = window.TRANSLATIONS[msg] || msg
    if (typeof msg.replace !== 'function') {
        // eslint-disable-next-line no-console
        console.error('no replace method on message instance!')
        // eslint-disable-next-line no-console
        console.error(msg)
        return ''
    }

    return msg.replace(/{(\d+)}/g, function (match, number) {
        return typeof args[number] != 'undefined' ? args[number] : match
    })
}

export type TranslateFunction = (msg: string, ...args: any[]) => string

export {translate}
