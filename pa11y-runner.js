

const chalk = require('chalk');
const defaults = require('lodash/defaultsDeep');
const pa11y = require('pa11y');
const queue = require('async/queue');
const wordwrap = require('wordwrap');


const config = require('./a11y-config');


// Just an empty function to use as default
// configuration and arguments
/* istanbul ignore next */
const noop = () => {};

// The default configuration object. This is extended with
// whatever configurations the user passes in from the
// command line
const optsDefaults = {
    defaultHost: process.env.A11Y_HOST,
    urls: [],
    concurrency: 2,
    // fake log because we don't want it to
    // get passed into Pa11y – we don't want super verbose
    // logs from it
    log: {
        error: noop,
        info: noop,
        debug: noop,
    },
    wrapWidth: 80,
};

// Default the passed in options
const options = defaults({}, config, optsDefaults);

const log = console;

// Create a Pa11y test function and an async queue
const taskQueue = queue(testRunner, options.concurrency);
taskQueue.drain = testRunComplete;

// Push the URLs on to the queue
log.info(chalk.cyan.underline(`Running Pa11y on ${options.urls.length} URLs:`));
taskQueue.push(options.urls);

// The report object is what we eventually return to
// the user or command line runner
const report = {
    total: options.urls.length,
    passes: 0,
    errors: 0,
    results: {},
};

// This is the actual test runner, which the queue will
// execute on each of the URLs
async function testRunner(urlConfig) {
    let url, localConfig;
    if (typeof urlConfig === 'string') {
        url = urlConfig;
        localConfig = options.defaults;
    } else {
        url = urlConfig.url;
        localConfig = defaults({}, urlConfig, options.defaults);
    }

    if (!url.startsWith('http')) {
        if (!options.defaultHost) {
            log.error('if url is not absolute you should provide `A11Y_HOST` env variable');
            process.exit(1);
        }
        url = `${options.defaultHost}${url}`;
    }

    // Run the Pa11y test on the current URL and add
    // results to the report object

    try {
        const results = await pa11y(url, localConfig);

        if (results.issues.length) {
            report.results[url] = results.issues;
            report.errors += results.issues.length;
        } else {
            report.results[url] = [];
            report.passes += 1;
        }
    } catch (error) {
        log.error(` ${chalk.cyan('>')} ${url} - ${chalk.red('Failed to run')}`);
        report.results[url] = [error];
    }

}

// This function is called once all of the URLs in the
// queue have been tested. It outputs the actual errors
// that occurred in the test as well as a pass/fail ratio
function testRunComplete() {
    const passRatio = `${report.passes}/${report.total} URLs passed`;

    if (report.passes === report.total) {
        log.info(chalk.green(`\n✔ ${passRatio}`));
    } else {

        // Now we loop over the errors and output them with
        // word wrapping
        const wrap = wordwrap(3, options.wrapWidth);
        Object.keys(report.results).forEach(url => {
            if (report.results[url].length) {
                log.error(chalk.underline(`\nErrors in ${url}:`));
                report.results[url].forEach(result => {
                    const redBullet = chalk.red('•');
                    if (result instanceof Error) {
                        log.error(`\n ${redBullet} Error: ${wrap(result.message).trim()}`);
                    } else {
                        log.error([
                            '',
                            ` ${redBullet} ${wrap(result.message).trim()}`,
                            '',
                            chalk.grey(wrap(`(${result.selector})`)),
                            '',
                            chalk.grey(wrap(result.context.replace(/[\r\n]+\s+/, ' '))),
                        ].join('\n'));
                    }
                });
            }
        });
        log.info(chalk.cyan.underline('\nSummary'));
        for (let [url, issues] of Object.entries(report.results)) {
            let message = ` ${chalk.cyan('>')} ${url} - `;
            if (issues.length) {
                message += chalk.red(`${issues.length} errors`);
                log.error(message);
            } else {
                message += chalk.green(`${issues.length} errors`);
                log.info(message);
            }
        }
        log.error(chalk.red(`\n✘ ${passRatio}`));
    }

}

