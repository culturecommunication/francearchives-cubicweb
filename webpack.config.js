'use strict'

const path = require('path')
const webpack = require('webpack')

const config = {
    context: path.join(__dirname, 'appjs'),
    entry: {
        'circular-table': ['./circular-table'],
        'pnialocation-map': ['./pnialocation-map'],
        'pniaservices-map': ['./pniaservices-map'],
        'pniaservice-map': ['./pniaservice-map'],
        glossary: ['./glossary'],
        'pnia-toc': ['./pnia-toc'],
        'pnia-faq': ['./pnia-faq'],
        'intro-tour': ['./introjs'],
        'pnia-sectiontree': ['./pnia-sectiontree.js'],
        'pnia-mainmenu': ['./pnia-mainmenu.js'],
        'pnia-mirador': ['./pnia-mirador.js'],
        'advanced-search': ['./advanced-search/main.tsx'],
        yasgui: ['./yasgui/index.tsx'],
    },
    module: {
        rules: [
            {
                test: /\.js$/,
                exclude: /node_modules/,
                loader: 'babel-loader',
                options: {
                    cacheDirectory: true,
                },
            },
            {
                test: /\.tsx?$/,
                exclude: /node_modules/,
                use: ['ts-loader'],
            },
            {
                test: /\.css$/,
                use: ['style-loader', 'css-loader'],
            },
        ],
    },
    output: {
        filename: 'bundle-[name].js',
        path: path.join(__dirname, 'cubicweb_francearchives', 'data'),
    },
    plugins: [
        new webpack.IgnorePlugin({
            resourceRegExp: /^(buffertools)$/,
        }), // unwanted "deeper" dependency
    ],
    resolve: {
        fallback: {
            url: false,
            '@blueprintjs/core': false,
            '@blueprintjs/icons': false,
        },
        // don't include a normalize-url for mirador, if neededfall back on an other polyfill
        // also get ride of warnings on unused '@blueprintjs/core' and  '@blueprintjs/icons'
        extensions: ['.ts', '.tsx', '.js', '.json'],
    },
}

if (process.env.FA_DEV) {
    // transpile need 0.5s
    delete config.module
}

module.exports = (env, argv) => {
    if (argv.mode === 'production') {
        // install polyfills for production
        config.plugins.push(
            new webpack.DefinePlugin({
                'process.env': {
                    NODE_ENV: JSON.stringify('production'),
                },
            }),
        )
    }

    return config
}
