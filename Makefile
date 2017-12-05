caars:
	jbuilder build
	cp _build/default/app/caars_app.exe caars
test:
	cd example && bash Launch_CAARS.sh

test2:
	cd example && bash Launch_CAARS2.sh

clean_test:
	cd example && (rm -r working_dir/ output_dir/ || exit 0)

clean_test2:
	cd example && (rm -r working2_dir/ output2_dir/ || exit 0)

clean:
	ocamlbuild -clean
	rm -f utils/lib/*.pyc

build_caars_env_docker:
	cd etc && ./build_caars_env.sh
build_caars_docker:
	cd etc && ./build_caars.sh
build_caars_dev_docker:
	cd etc && ./build_caars_dev.sh

.PHONY: caars test clean_test clean test2 clean_test2 build_caars_env_docker build_caars_docker build_caars_dev_docker
