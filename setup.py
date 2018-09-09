import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="droplet_dove",
    version="0.0.3",
    author="Vishal Kuo",
    author_email="vishalkuo@gmail.com",
    description="A utility to manage a development server on digital ocean",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/vishalkuo/dove",
    packages=setuptools.find_packages(),
    install_requires=["python-digitalocean", "click"],
    classifiers=[
        "Programming Language :: Python :: 3.6",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={"console_scripts": ["dove = dove.dove:cli"]},
)
