Pod::Spec.new do |s|
  s.name             = 'lumiface'
  s.version          = '0.3.0'
  s.summary          = 'Face verification with active liveness: Apple Vision face detection for the Lumiface Flutter package.'
  s.description      = 'Runs VNDetectFaceRectanglesRequest on the camera frames the Dart side streams.'
  s.homepage         = 'https://github.com/GA-MO/lumiface'
  s.license          = { :type => 'MIT', :file => '../LICENSE' }
  s.author           = { 'Lumiface' => 'hello@lumiface.ai' }
  s.source           = { :path => '.' }
  s.source_files     = 'Classes/**/*'
  s.dependency 'Flutter'
  s.frameworks       = 'Vision', 'CoreVideo', 'VideoToolbox', 'Accelerate'
  s.platform         = :ios, '13.0'
  s.swift_version    = '5.0'
  s.pod_target_xcconfig = { 'DEFINES_MODULE' => 'YES', 'EXCLUDED_ARCHS[sdk=iphonesimulator*]' => 'i386' }
end
