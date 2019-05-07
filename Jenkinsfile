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
        sh 'tox -e flake8'
    }
    stage('Test') {
        timeout(time: 1, unit: 'HOURS') {
          withEnv(["PATH+POSTGRESQL=/usr/lib/postgresql/9.6/bin"]) {
            sh 'tox -e py27'
          }
        }
    }
}
