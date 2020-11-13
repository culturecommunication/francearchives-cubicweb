'use strict';


const path = require('path');
const webpack = require('webpack');


const config = module.exports = {
    context: path.join(__dirname, 'appjs'),
    entry: {
        'circular-table': ['./circular-table'],
        'pnialocation-map': ['./pnialocation-map'],
        'glossary': ['./glossary'],
        'pnia-toc': ['./pnia-toc'],
        'pnia-faq': ['./pnia-faq'],
    },
    module: {
        loaders: [
            {
                test: /\.js$/,
                exclude: /node_modules/,
                loader: "babel-loader?cacheDirectory",
            },
        ],
    },
    output: {
        filename: 'bundle-[name].js',
        path: path.join(__dirname, 'cubicweb_francearchives', 'data'),
    },
    plugins: [
        new webpack.IgnorePlugin(/^(buffertools)$/), // unwanted "deeper" dependency
    ],
};


if (process.env.FA_DEV) {
    // transpile need 0.5s
    delete config.module;
}


if (process.env.NODE_ENV === 'production') {
    // install polyfills for production
    config.plugins.push(
        new webpack.optimize.UglifyJsPlugin(),
        new webpack.DefinePlugin({
            "process.env": {
                NODE_ENV: JSON.stringify('production'),
            },
        })
    );
}
