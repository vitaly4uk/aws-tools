from distutils.core import setup

setup(
    name='aws-tools',
    version='0.1',
    packages=['aws-tools'],
    url='http://github.com/vitaly4uk/aws-tools',
    license=open('LICENSE').read(),
    author='vitaly omelchuk',
    author_email='vitaly.omelchuk@gmail.com',
    description='tools to create projects on vps',
    data_files=[
        ('/var/lib/aws-tools', [
            'aws-tools/templates/template_nginx',
            'aws-tools/templates/template_settings',
            'aws-tools/templates/template_supervisor',
            'README.md'])
    ],
    scripts=['aws-tools/new_domain.py']
)
