from distutils.core import setup
from aws_tools import VERSION

setup(
    name='aws-tools',
    version='.'.join(map(str, VERSION)),
    packages=['aws_tools'],
    url='http://github.com/vitaly4uk/aws-tools',
    license='GPL v3',
    author='vitaly omelchuk',
    author_email='vitaly.omelchuk@gmail.com',
    description='tools to create projects on vps',
    data_files=[
        ('/var/lib/aws-tools', [
            'aws_tools/templates/template_nginx',
            'aws_tools/templates/template_settings',
            'aws_tools/templates/template_supervisor',
            'README.md'])
    ],
    scripts=['aws_tools/new_domain.py']
)
