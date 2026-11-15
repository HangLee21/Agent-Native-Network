# Windows 运行环境

本目录的 python/ 为 Windows x64 CPython 3.11.5，包含 esptool 4.13.0、pyserial 3.5 及依赖 bitstring 4.4.0、bitarray 3.12.2、tibs 0.5.7、cryptography 44.0.3、cffi 2.1.1、pycparser 3.12、ecdsa 0.19.2、intelhex 2.3.0、PyYAML 6.0.3、reedsolo 1.7.0、six 1.17.0。运行环境中的 LICENSE.txt 和各包 dist-info 留存许可证；RUNTIME_SHA256.json 记录复制时的文件摘要。

交付人员重新准备环境时，请使用可信来源的 Windows x64 CPython 3.11.5，将上述固定版本及依赖安装到隔离环境，并核对许可证与 SHA-256 后生成 runtime/python。正常双击不需要用户安装 Python 或选择端口。其他电脑的兼容性尚未验证。
