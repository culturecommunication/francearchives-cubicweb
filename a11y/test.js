const pa11y = require('pa11y');
let baseURL = process.env.BASEURL;
if (baseURL.endsWith('/')) {
     baseURL = baseURL.slice(0,-1);
}

const testCases = require('./testcases');

for (let testCase of testCases){
    let testUrl = baseURL + testCase.url,
        errors = [];
    console.log('--------------------------------------------------');
    console.log('url "%s"', testUrl);
    pa11y(testUrl, {
        "chromeLaunchConfig": {
            "args": ["--no-sandbox", "--disable-setuid-sandbox"]}
    }).then((results) => {
        if (results.issues.length > 0){
            let ignores = testCase.ignores,
            ig = null;
            for (let result of results.issues) {
                for (let ignore of ignores) {
                    if (result.code === ignore.code && result.selector === ignore.selector) {
                        ig = result;
                        break;
                    }
                }
                if (ig !== result) {
                    errors.push(result);
                }
            }
        if (errors.length > 0) {
            console.log('url "%s" failed (%s errors)', testUrl, errors.length);
            for (let error of errors) {
                console.log('\n  code: %s', error['code']);
                console.log('  message: %s', error['message']);
                console.log('  selector: %s', error['selector']);
                console.log('  type: %s \n', error['type']);

            }
        }
        }
    }).catch((error) => {
        console.log(error);
    });

}
