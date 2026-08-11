source "https://rubygems.org"

gem "fastlane", "~> 2.220"
gem "plist", "~> 3.7"
# Bundler 4 要求显式声明间接依赖，否则 fastlane 启动时会报 Gem::LoadError
gem "multi_json", "~> 1.11"

plugins_path = File.join(File.dirname(__FILE__), 'fastlane', 'Pluginfile')
eval_gemfile(plugins_path) if File.exist?(plugins_path)
