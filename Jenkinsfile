#!groovy
node('debian_stretch') {
    stage('Setup') {
        if (env.DESCRIPTION) {
            currentBuild.description = env.DESCRIPTION
        }
        checkout scm
        if (env.DIFF_ID) {
            sh('hg phabread --stack ' + env.DIFF_ID + ' | hg import -')
        }
        sh('sudo apt-get install -y poppler-utils')
    }
    stage('Lint') {
        parallel (
            'flake8': {
                sh 'tox -e flake8'
            },
            'dodgy': {
                sh 'tox -e dodgy'
            },
            'check-manifest': {
                sh 'tox -e check-manifest'
            }
        )
    }
    stage('Test') {
        timeout(time: 1, unit: 'HOURS') {
          withEnv(["PATH+POSTGRESQL=/usr/lib/postgresql/9.6/bin",
                   "FRARCHIVES_NO_BUILD_DATA_FILES=1"]) {
            sh 'tox -e py3'
          }
        }
    }
}
