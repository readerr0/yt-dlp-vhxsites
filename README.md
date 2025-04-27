This repository contains extractors for some VHX (Vimeo Embed) based websites, based on the original dropout extractor used in yt-dlp

See [yt-dlp plugins](https://github.com/yt-dlp/yt-dlp#plugins) for more details.


## Installation

Requires yt-dlp `2023.01.02` or above.

You can install this package with pip:
```
python3 -m pip install -U https://github.com/readerr0/yt-dlp-vhxsites/archive/master.zip
```

See [installing yt-dlp plugins](https://github.com/yt-dlp/yt-dlp#installing-plugins) for the other methods this plugin package can be installed.

## Usage

IMPORTANT: You will need to use a netrc file with these extractors as the -U/--Username and -P/--Password wont work, make sure to use the relevant netrc flag in yt-dlp (ie --netrc-location PATH)

Example netrc file
```
machine 2ndtry login email@address.com password c00lp@ssw0rd
machine wowpresentsplus login email@address.com password c00lp@ssw0rd
```
