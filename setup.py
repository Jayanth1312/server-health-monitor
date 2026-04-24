from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="server-health-monitor",
    version="1.1.0",
    author="Jayanth Paladugu",
    author_email="jayanthpaladugu3@gmail.com",
    description="Lightweight cross-platform server health monitor with TUI and email alerts (Linux, macOS, Windows)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Jayanth1312/server-health-monitor",
    packages=find_packages(),
    package_data={
        "monitor": [
            "monitor.service",
            "config.default.yaml",
        ],
    },
    python_requires=">=3.9",
    install_requires=[
        "psutil>=5.9.0",
        "PyYAML>=6.0",
        "loguru>=0.7.0",
        "pydantic>=2.0.0",
        # stdlib `curses` is not shipped on Windows — this fills in.
        'windows-curses>=2.3.0; platform_system == "Windows"',
    ],
    entry_points={
        "console_scripts": [
            "monitor=monitor.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: OS Independent",
        "Topic :: System :: Monitoring",
        "Environment :: Console :: Curses",
        "Intended Audience :: System Administrators",
    ],
    keywords="server monitor health cpu memory disk alerts tui linux macos windows cross-platform",
)
