%if 0%{?rhel} == 6
  %global python_ver 2.6
%else
  %global python_ver 2.7
%endif

Summary: Arsenal client python library.
Name: arsenal-client-lib
Version: 0.1
Release: 0.1%{?dist}
License: Proprietary
Group: System/Tools
URL: http://docs.python-requests.org/en/latest/

BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root
BuildArch: noarch
# Disable automatic dependency checking
Autoreqprov: 0
Autoreq: 0

%description
Arsenal client python library for python %{python_ver}. Created for use
with system python.

%pre

%prep

%build

%install
rm -rf $RPM_BUILD_ROOT
mkdir -p $RPM_BUILD_ROOT/usr/lib/python%{python_ver}/site-packages/
cp -R ../arsenalclientlib $RPM_BUILD_ROOT/usr/lib/python%{python_ver}/site-packages/

%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root,-)

%attr(755, root, root) /usr/lib/python%{python_ver}/site-packages/arsenalclientlib

%post

